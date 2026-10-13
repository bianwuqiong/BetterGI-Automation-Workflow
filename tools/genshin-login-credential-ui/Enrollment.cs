using System.Security.Cryptography;
using System.Text;
using System.Text.Json;

namespace GenshinLoginCredentialUI;

internal static class Policy
{
    internal const string Reference = "BetterGI-Automation-Workflow/GenshinImpact/International/Main";
    internal const string Scope = "loginOnly";
    internal static void Validate(string reference) { if (reference != Reference) throw new InvalidOperationException(); }
}

internal sealed record Status(bool Success, bool Exists, bool AutomationAllowed, string CredentialRef);
internal sealed record Receipt(int Version, string CredentialRef, string UserSid, string Scope,
    bool AutomationAllowed, string EnrollmentId, string CreatedUtc);

// These internal boundaries pass encrypted bytes only, never a password getter or injection callback.
internal interface ICredentialBackend
{
    bool Exists(string reference);
    byte[]? ReadProtectedBlob(string reference);
    void WriteProtectedBlob(string reference, byte[] accountUtf8, byte[] protectedBlob, bool allowOverwrite);
}
internal interface IDataProtection { byte[] Protect(byte[] bytes); byte[] Unprotect(byte[] bytes); }
internal interface IReceiptStore { byte[]? Read(); void WriteAtomic(byte[] bytes); }

internal static class SecretMemory
{
    internal static void Clear(byte[]? bytes) { if (bytes is not null) CryptographicOperations.ZeroMemory(bytes); }
}

internal sealed class EnrollmentService(ICredentialBackend backend, IDataProtection protection, IReceiptStore receipts, string userSid)
{
    internal Status Save(string reference, byte[] account, byte[] password, bool automationAllowed, bool allowOverwrite)
    {
        byte[]? envelope = null, encryptedEnvelope = null, receiptPayload = null, signature = null, receiptPacket = null, encryptedReceipt = null;
        byte[] key = RandomNumberGenerator.GetBytes(32);
        try
        {
            Policy.Validate(reference);
            if (!ValidInput(account) || !ValidInput(password))
                return new(false, false, false, Policy.Reference);
            if (backend.Exists(reference) && !allowOverwrite) return new(false, true, false, Policy.Reference);
            string id = Guid.NewGuid().ToString("D");
            var receipt = new Receipt(1, reference, userSid, Policy.Scope, automationAllowed, id, DateTimeOffset.UtcNow.ToString("O"));
            receiptPayload = JsonSerializer.SerializeToUtf8Bytes(receipt);
            signature = HMACSHA256.HashData(key, receiptPayload);
            receiptPacket = Packet(receiptPayload, signature);
            encryptedReceipt = protection.Protect(receiptPacket);
            envelope = Packet(Encoding.ASCII.GetBytes("BGI1"), Guid.Parse(id).ToByteArray(), key, account, password);
            encryptedEnvelope = protection.Protect(envelope);
            if (encryptedEnvelope.Length > 2560) return new(false, false, false, Policy.Reference);
            // Receipt preparation succeeds before touching WinCred. Credential then receipt commit:
            // a partial failure has no matching receipt and therefore fails closed.
            backend.WriteProtectedBlob(reference, account, encryptedEnvelope, allowOverwrite);
            receipts.WriteAtomic(encryptedReceipt);
            var verified = Status(reference);
            return verified.Success && verified.Exists && verified.AutomationAllowed == automationAllowed
                ? verified : new(false, verified.Exists, false, Policy.Reference);
        }
        catch { return new(false, false, false, Policy.Reference); }
        finally
        {
            foreach (var bytes in new[] { envelope, encryptedEnvelope, receiptPayload, signature, receiptPacket, encryptedReceipt, key }) SecretMemory.Clear(bytes);
        }
    }

    private static bool ValidInput(byte[] utf8)
    {
        if (utf8.Length is < 1 or > 1024) return false;
        char[] chars = new char[utf8.Length];
        try
        {
            int count = new UTF8Encoding(false, true).GetChars(utf8, chars);
            if (count is < 1 or > 256) return false;
            for (int i = 0; i < count; i++) if (char.IsControl(chars[i])) return false;
            return true;
        }
        finally { Array.Clear(chars); }
    }

    internal Status Status(string reference)
    {
        byte[]? encrypted = null, plain = null, encryptedReceipt = null, receiptPlain = null;
        List<byte[]>? fields = null, receiptFields = null;
        bool exists = false;
        try
        {
            Policy.Validate(reference);
            encrypted = backend.ReadProtectedBlob(reference);
            exists = encrypted is not null;
            if (!exists) return new(true, false, false, Policy.Reference);
            encryptedReceipt = receipts.Read();
            if (encryptedReceipt is null) return new(true, true, false, Policy.Reference);
            plain = protection.Unprotect(encrypted!);
            receiptPlain = protection.Unprotect(encryptedReceipt);
            fields = ParsePacket(plain, 5);
            receiptFields = ParsePacket(receiptPlain, 2);
            if (!fields[0].AsSpan().SequenceEqual("BGI1"u8) || fields[1].Length != 16 || fields[2].Length != 32) throw new InvalidOperationException();
            byte[] expected = HMACSHA256.HashData(fields[2], receiptFields[0]);
            try { if (!CryptographicOperations.FixedTimeEquals(expected, receiptFields[1])) throw new InvalidOperationException(); }
            finally { SecretMemory.Clear(expected); }
            var receipt = JsonSerializer.Deserialize<Receipt>(receiptFields[0]) ?? throw new InvalidOperationException();
            bool valid = receipt.Version == 1 && receipt.CredentialRef == Policy.Reference && receipt.UserSid == userSid &&
                receipt.Scope == Policy.Scope && receipt.EnrollmentId == new Guid(fields[1]).ToString("D");
            return new(true, true, valid && receipt.AutomationAllowed, Policy.Reference);
        }
        catch { return new(false, exists, false, Policy.Reference); }
        finally
        {
            foreach (var bytes in new[] { encrypted, plain, encryptedReceipt, receiptPlain }) SecretMemory.Clear(bytes);
            if (fields is not null) foreach (var bytes in fields) SecretMemory.Clear(bytes);
            if (receiptFields is not null) foreach (var bytes in receiptFields) SecretMemory.Clear(bytes);
        }
    }

    // Every field is a little-endian Int32 length followed by bytes; packet has no trailing data.
    internal static byte[] Packet(params byte[][] parts)
    {
        int length = parts.Sum(x => checked(4 + x.Length));
        var result = new byte[length]; int offset = 0;
        foreach (var part in parts) { System.Buffers.Binary.BinaryPrimitives.WriteInt32LittleEndian(result.AsSpan(offset, 4), part.Length); offset += 4; part.CopyTo(result, offset); offset += part.Length; }
        return result;
    }

    internal static List<byte[]> ParsePacket(byte[] packet, int count)
    {
        var result = new List<byte[]>(); int offset = 0;
        try
        {
            for (int i = 0; i < count; i++)
            {
                if (packet.Length - offset < 4) throw new InvalidOperationException();
                int length = System.Buffers.Binary.BinaryPrimitives.ReadInt32LittleEndian(packet.AsSpan(offset, 4)); offset += 4;
                if (length < 0 || length > packet.Length - offset) throw new InvalidOperationException();
                result.Add(packet.AsSpan(offset, length).ToArray()); offset += length;
            }
            if (offset != packet.Length) throw new InvalidOperationException();
            return result;
        }
        catch { foreach (var field in result) SecretMemory.Clear(field); throw; }
    }
}
