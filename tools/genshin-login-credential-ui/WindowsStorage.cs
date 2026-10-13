using System.ComponentModel;
using System.Runtime.InteropServices;
using System.Security.AccessControl;
using System.Security.Principal;
using System.Text;

namespace GenshinLoginCredentialUI;

internal sealed class WindowsCredentials : ICredentialBackend
{
    private const int NotFound = 1168;

    public bool Exists(string reference)
    {
        var bytes = ReadProtectedBlob(reference);
        try { return bytes is not null; }
        finally { SecretMemory.Clear(bytes); }
    }

    public byte[]? ReadProtectedBlob(string reference)
    {
        Policy.Validate(reference);
        if (!CredRead(reference, 1, 0, out IntPtr pointer))
        {
            if (Marshal.GetLastWin32Error() == NotFound) return null;
            throw new InvalidOperationException("Credential operation failed.");
        }
        NativeCredential credential = default;
        try
        {
            credential = Marshal.PtrToStructure<NativeCredential>(pointer);
            if (credential.CredentialBlobSize > 2560 || credential.CredentialBlobSize == 0) throw new InvalidOperationException();
            byte[] bytes = new byte[credential.CredentialBlobSize];
            Marshal.Copy(credential.CredentialBlob, bytes, 0, bytes.Length);
            return bytes;
        }
        finally
        {
            NativeMemory.Clear(credential.CredentialBlob, checked((int)credential.CredentialBlobSize));
            CredFree(pointer);
        }
    }

    public void WriteProtectedBlob(string reference, byte[] accountUtf8, byte[] protectedBlob, bool allowOverwrite)
    {
        Policy.Validate(reference);
        if (!allowOverwrite && Exists(reference)) throw new InvalidOperationException();
        if (protectedBlob.Length is < 1 or > 2560) throw new InvalidOperationException();
        char[] chars = new char[Encoding.UTF8.GetCharCount(accountUtf8)];
        byte[] username = new byte[checked(chars.Length * 2 + 2)];
        GCHandle userPin = default, blobPin = default;
        try
        {
            Encoding.UTF8.GetChars(accountUtf8, chars);
            Encoding.Unicode.GetBytes(chars.AsSpan(), username.AsSpan());
            userPin = GCHandle.Alloc(username, GCHandleType.Pinned);
            blobPin = GCHandle.Alloc(protectedBlob, GCHandleType.Pinned);
            var credential = new NativeCredential
            {
                Type = 1, TargetName = Policy.Reference, CredentialBlobSize = (uint)protectedBlob.Length,
                CredentialBlob = blobPin.AddrOfPinnedObject(), Persist = 2, UserName = userPin.AddrOfPinnedObject()
            };
            if (!CredWrite(ref credential, 0)) throw new InvalidOperationException("Credential operation failed.");
        }
        finally
        {
            Array.Clear(chars); SecretMemory.Clear(username);
            if (userPin.IsAllocated) userPin.Free();
            if (blobPin.IsAllocated) blobPin.Free();
        }
    }

    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Unicode)]
    private struct NativeCredential
    {
        public uint Flags; public uint Type;
        [MarshalAs(UnmanagedType.LPWStr)] public string? TargetName;
        public IntPtr Comment; public System.Runtime.InteropServices.ComTypes.FILETIME LastWritten;
        public uint CredentialBlobSize; public IntPtr CredentialBlob; public uint Persist;
        public uint AttributeCount; public IntPtr Attributes; public IntPtr TargetAlias; public IntPtr UserName;
    }
    [DllImport("advapi32.dll", EntryPoint = "CredReadW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CredRead(string target, uint type, uint flags, out IntPtr credential);
    [DllImport("advapi32.dll", EntryPoint = "CredWriteW", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CredWrite(ref NativeCredential credential, uint flags);
    [DllImport("advapi32.dll")] private static extern void CredFree(IntPtr buffer);
}

internal static class NativeMemory
{
    internal static unsafe void Clear(IntPtr pointer, int length)
    {
        if (pointer != IntPtr.Zero && length > 0) new Span<byte>(pointer.ToPointer(), length).Clear();
    }
}

internal sealed class Dpapi : IDataProtection
{
    // Fixed, public domain separation; the user's DPAPI key provides confidentiality/integrity.
    private static readonly byte[] Entropy = Encoding.UTF8.GetBytes("BGI/GenshinImpact/International/Main/v1/loginOnly");
    public byte[] Protect(byte[] bytes) => Transform(bytes, true);
    public byte[] Unprotect(byte[] bytes) => Transform(bytes, false);

    private static byte[] Transform(byte[] input, bool protect)
    {
        GCHandle inputPin = default, entropyPin = default;
        Blob output = default;
        try
        {
            inputPin = GCHandle.Alloc(input, GCHandleType.Pinned);
            entropyPin = GCHandle.Alloc(Entropy, GCHandleType.Pinned);
            var inBlob = new Blob { Length = input.Length, Data = inputPin.AddrOfPinnedObject() };
            var entropy = new Blob { Length = Entropy.Length, Data = entropyPin.AddrOfPinnedObject() };
            // CRYPTPROTECT_UI_FORBIDDEN; never CRYPTPROTECT_LOCAL_MACHINE.
            bool ok = protect ? CryptProtectData(ref inBlob, null, ref entropy, IntPtr.Zero, IntPtr.Zero, 1, out output)
                : CryptUnprotectData(ref inBlob, IntPtr.Zero, ref entropy, IntPtr.Zero, IntPtr.Zero, 1, out output);
            if (!ok || output.Length is < 1 or > 16384) throw new InvalidOperationException("Data protection failed.");
            var result = new byte[output.Length]; Marshal.Copy(output.Data, result, 0, result.Length); return result;
        }
        finally
        {
            NativeMemory.Clear(output.Data, output.Length);
            if (output.Data != IntPtr.Zero) LocalFree(output.Data);
            if (inputPin.IsAllocated) inputPin.Free();
            if (entropyPin.IsAllocated) entropyPin.Free();
        }
    }
    [StructLayout(LayoutKind.Sequential)] private struct Blob { public int Length; public IntPtr Data; }
    [DllImport("crypt32.dll", CharSet = CharSet.Unicode, SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CryptProtectData(ref Blob data, string? description,
        ref Blob entropy, IntPtr reserved, IntPtr prompt, uint flags, out Blob output);
    [DllImport("crypt32.dll", SetLastError = true)]
    [return: MarshalAs(UnmanagedType.Bool)] private static extern bool CryptUnprotectData(ref Blob data, IntPtr description,
        ref Blob entropy, IntPtr reserved, IntPtr prompt, uint flags, out Blob output);
    [DllImport("kernel32.dll")] private static extern IntPtr LocalFree(IntPtr memory);
}

internal sealed class PrivateReceiptStore(string directory, string sid) : IReceiptStore
{
    private string ReceiptPath => Path.Combine(directory, "authorization.receipt.dpapi");
    public byte[]? Read()
    {
        if (!File.Exists(ReceiptPath)) return null;
        var info = new FileInfo(ReceiptPath);
        if (info.Length is < 1 or > 16384) throw new InvalidOperationException();
        return File.ReadAllBytes(ReceiptPath);
    }
    public void WriteAtomic(byte[] bytes)
    {
        var security = new DirectorySecurity();
        security.SetAccessRuleProtection(true, false);
        var inheritance = InheritanceFlags.ContainerInherit | InheritanceFlags.ObjectInherit;
        security.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(sid), FileSystemRights.FullControl, inheritance, PropagationFlags.None, AccessControlType.Allow));
        security.AddAccessRule(new FileSystemAccessRule(new SecurityIdentifier(WellKnownSidType.LocalSystemSid, null), FileSystemRights.FullControl, inheritance, PropagationFlags.None, AccessControlType.Allow));
        var info = new DirectoryInfo(directory);
        if (!info.Exists) info.Create(security); else info.SetAccessControl(security);
        string temporary = Path.Combine(directory, Guid.NewGuid().ToString("N") + ".pending.dpapi");
        // A write failure may leave an encrypted pending receipt for recoverable inspection.
        using (var stream = new FileStream(temporary, FileMode.CreateNew, FileAccess.Write, FileShare.None))
        { stream.Write(bytes); stream.Flush(true); }
        File.Move(temporary, ReceiptPath, true);
    }
}
