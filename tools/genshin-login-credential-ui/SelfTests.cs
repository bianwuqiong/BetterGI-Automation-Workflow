using System.Security.Cryptography;
using System.Text;

namespace GenshinLoginCredentialUI;

internal static class SelfTests
{
    private static int passed;
    internal static int Run()
    {
        try
        {
            Check("invalid input has no writes", () => { var f = Fixture(); var result = f.Service.Save(Policy.Reference, [], "fixture-password"u8.ToArray(), true, false); Require(!result.Success && f.Backend.Writes == 0 && f.Receipts.Writes == 0); });
            Check("foreign ref has no writes", () => { var f = Fixture(); var result = f.Service.Save("foreign", "fixture-account"u8.ToArray(), "fixture-password"u8.ToArray(), true, false); Require(!result.Success && f.Backend.Reads == 0 && f.Backend.Writes == 0 && !f.Service.Status("foreign").Success); });
            Check("unchecked consent stays disabled", () => { var f = Fixture(); Require(Save(f, false).Success && !f.Service.Status(Policy.Reference).AutomationAllowed); });
            Check("checked consent is receipt bound", () => { var f = Fixture(); Require(Save(f, true).AutomationAllowed); var wrong = new EnrollmentService(f.Backend, f.Protection, f.Receipts, "S-1-test-other"); Require(!wrong.Status(Policy.Reference).AutomationAllowed); });
            Check("existing target cannot silently overwrite", () => { var f = Fixture(); Save(f, false); var previous = f.Backend.Blob!.ToArray(); Require(!Save(f, true).Success && f.Backend.Writes == 1 && previous.SequenceEqual(f.Backend.Blob!)); SecretMemory.Clear(previous); });
            Check("explicit overwrite permits replacing", () => { var f = Fixture(); Save(f, false); Require(Save(f, true, true).AutomationAllowed && f.Backend.Writes == 2); });
            Check("protect failure has no writes", () => { var f = Fixture(); f.Protection.Fail = true; Require(!Save(f, true).Success && f.Backend.Writes == 0 && f.Receipts.Writes == 0); });
            Check("backend failure does not commit receipt", () => { var f = Fixture(); f.Backend.Fail = true; Require(!Save(f, true).Success && f.Backend.Blob is null && f.Receipts.Writes == 0); });
            Check("receipt failure cannot enable automation", () => { var f = Fixture(); Save(f, true); f.Receipts.Fail = true; Require(!Save(f, true, true).Success && !f.Service.Status(Policy.Reference).AutomationAllowed); });
            Check("tampered receipt disables automation", () => { var f = Fixture(); Save(f, true); f.Receipts.Blob![10] ^= 1; Require(!f.Service.Status(Policy.Reference).AutomationAllowed); });
            Check("owned secret buffers cleared after save/status", () => { var f = Fixture(); Save(f, true); f.Service.Status(Policy.Reference); Require(f.Protection.Owned.All(x => x.All(b => b == 0)) && f.Backend.ReadCopies.All(x => x.All(b => b == 0)) && f.Receipts.ReadCopies.All(x => x.All(b => b == 0))); });
            Check("partial packet parsing rejected", () => { byte[] malformed = EnrollmentService.Packet("fixed"u8.ToArray(), "fixed2"u8.ToArray()); Array.Resize(ref malformed, malformed.Length - 1); bool rejected = false; try { EnrollmentService.ParsePacket(malformed, 2); } catch (InvalidOperationException) { rejected = true; } finally { SecretMemory.Clear(malformed); } Require(rejected); });
            Check("native owned buffer zeroized", () =>
            {
                var pointer = System.Runtime.InteropServices.Marshal.AllocHGlobal(16);
                byte[] fixture = Enumerable.Repeat((byte)0x5A, 16).ToArray(), readback = new byte[16];
                try { System.Runtime.InteropServices.Marshal.Copy(fixture, 0, pointer, 16); NativeMemory.Clear(pointer, 16); System.Runtime.InteropServices.Marshal.Copy(pointer, readback, 0, 16); Require(readback.All(x => x == 0)); }
                finally { NativeMemory.Clear(pointer, 16); System.Runtime.InteropServices.Marshal.FreeHGlobal(pointer); SecretMemory.Clear(fixture); SecretMemory.Clear(readback); }
            });
            Console.WriteLine($"{{\"success\":true,\"fakeTestsPassed\":{passed},\"realCredentialAccess\":false}}");
            return 0;
        }
        catch { Console.WriteLine("{\"success\":false,\"fakeTestsPassed\":" + passed + ",\"realCredentialAccess\":false}"); return 1; }
    }
    private static void Check(string _, Action action) { action(); passed++; }
    private static void Require(bool condition) { if (!condition) throw new InvalidOperationException(); }
    private static Status Save(TestFixture f, bool enabled, bool overwrite = false)
    {
        byte[] account = "fixture-account"u8.ToArray(), password = FakePassword();
        try { return f.Service.Save(Policy.Reference, account, password, enabled, overwrite); }
        finally { SecretMemory.Clear(account); SecretMemory.Clear(password); }
    }
    // Synthetic input for the in-memory fake backend; never a real account credential.
    private static byte[] FakePassword() => "fixture-password"u8.ToArray();
    private static TestFixture Fixture()
    {
        var backend = new FakeBackend(); var protection = new FakeProtection(); var receipts = new FakeReceipts();
        return new(backend, protection, receipts, new EnrollmentService(backend, protection, receipts, "S-1-test-current"));
    }
    private sealed record TestFixture(FakeBackend Backend, FakeProtection Protection, FakeReceipts Receipts, EnrollmentService Service);
    private sealed class FakeBackend : ICredentialBackend
    {
        internal byte[]? Blob; internal int Writes, Reads; internal bool Fail; internal List<byte[]> ReadCopies = [];
        public bool Exists(string reference) { Policy.Validate(reference); Reads++; return Blob is not null; }
        public byte[]? ReadProtectedBlob(string reference) { Policy.Validate(reference); Reads++; if (Blob is null) return null; var copy = Blob.ToArray(); ReadCopies.Add(copy); return copy; }
        public void WriteProtectedBlob(string reference, byte[] accountUtf8, byte[] protectedBlob, bool allowOverwrite)
        { Policy.Validate(reference); if (Fail || (!allowOverwrite && Blob is not null)) throw new InvalidOperationException(); Blob = protectedBlob.ToArray(); Writes++; }
    }
    private sealed class FakeProtection : IDataProtection
    {
        internal bool Fail; internal List<byte[]> Owned = [];
        public byte[] Protect(byte[] bytes) { if (Fail) throw new InvalidOperationException(); Owned.Add(bytes); var result = bytes.ToArray(); Owned.Add(result); return result; }
        public byte[] Unprotect(byte[] bytes) { if (Fail) throw new InvalidOperationException(); var result = bytes.ToArray(); Owned.Add(result); return result; }
    }
    private sealed class FakeReceipts : IReceiptStore
    {
        internal byte[]? Blob; internal int Writes; internal bool Fail; internal List<byte[]> ReadCopies = [];
        public byte[]? Read() { if (Blob is null) return null; var result = Blob.ToArray(); ReadCopies.Add(result); return result; }
        public void WriteAtomic(byte[] bytes) { if (Fail) throw new InvalidOperationException(); Blob = bytes.ToArray(); Writes++; }
    }
}
