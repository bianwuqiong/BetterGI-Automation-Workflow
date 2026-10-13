using System.Text.Json;
using System.Security.Principal;

namespace GenshinLoginCredentialUI;

internal static class Program
{
    [STAThread]
    private static int Main(string[] args)
    {
        // No command accepts account/password, paths, foreign references, or enable flags.
        try
        {
            if (args.SequenceEqual(new[] { "--self-test" })) return SelfTests.Run();
            if (args.Length > 1 || (args.Length == 1 && args[0] != "--status" && args[0] != "--enroll"))
            {
                Print(new Status(false, false, false, Policy.Reference));
                return 2;
            }
            string sid = WindowsIdentity.GetCurrent().User?.Value ?? throw new InvalidOperationException();
            var service = new EnrollmentService(new WindowsCredentials(), new Dpapi(),
                new PrivateReceiptStore(Path.Combine(AppContext.BaseDirectory, "private-data"), sid), sid);
            if (args.SequenceEqual(new[] { "--status" }))
            {
                var status = service.Status(Policy.Reference);
                Print(status);
                return status.Success ? 0 : 1;
            }
            ApplicationConfiguration.Initialize();
            Application.SetUnhandledExceptionMode(UnhandledExceptionMode.CatchException);
            Application.ThreadException += (_, _) => MessageBox.Show("操作失败，未输出凭据。请关闭窗口后重试。", "安全录入");
            Application.Run(new EnrollmentForm(service));
            return 0;
        }
        catch
        {
            Print(new Status(false, false, false, Policy.Reference));
            return 1;
        }
    }

    internal static void Print(Status status) => Console.WriteLine(JsonSerializer.Serialize(status));
}

internal sealed class EnrollmentForm : Form
{
    private readonly EnrollmentService service;
    private readonly TextBox account = new() { MaxLength = 256, Width = 440, ShortcutsEnabled = false };
    private readonly TextBox password = new() { MaxLength = 256, Width = 440, UseSystemPasswordChar = true, ShortcutsEnabled = false };
    private readonly CheckBox consent = new() { AutoSize = false, Width = 450, Height = 65, Checked = false,
        Text = "允许本机 BGI 仅为此账号自动重新登录，验证码需我处理；不授权游戏消费" };
    private readonly Button save = new() { Text = "保存新凭据", AutoSize = true };
    private readonly Button overwrite = new() { Text = "明确覆盖已有凭据", AutoSize = true };
    private readonly Label state = new() { Width = 450, Height = 48 };

    internal EnrollmentForm(EnrollmentService service)
    {
        this.service = service;
        Text = "原神国际服 · 本机安全凭据录入";
        Width = 520; Height = 460; FormBorderStyle = FormBorderStyle.FixedDialog;
        MaximizeBox = false; MinimizeBox = false; StartPosition = FormStartPosition.CenterScreen;
        var layout = new FlowLayoutPanel { Dock = DockStyle.Fill, FlowDirection = FlowDirection.TopDown,
            WrapContents = false, Padding = new Padding(20), AutoScroll = true };
        layout.Controls.Add(new Label { Text = "请本人在此窗口手工输入。密码不会发送到聊天或日志。", AutoSize = true });
        layout.Controls.Add(new Label { Text = "账号", AutoSize = true }); layout.Controls.Add(account);
        layout.Controls.Add(new Label { Text = "密码", AutoSize = true }); layout.Controls.Add(password);
        layout.Controls.Add(consent);
        layout.Controls.Add(new Label { Text = "Windows 按当前用户加密存储；同一用户下的程序不受应用隔离。\n此工具仅录入凭据，不执行登录或游戏操作。", Width = 450, Height = 45 });
        layout.Controls.Add(state);
        var buttons = new FlowLayoutPanel { Width = 450, Height = 50 };
        buttons.Controls.Add(save); buttons.Controls.Add(overwrite);
        var cancel = new Button { Text = "取消", AutoSize = true };
        buttons.Controls.Add(cancel); layout.Controls.Add(buttons); Controls.Add(layout);
        cancel.Click += (_, _) => Close();
        save.Click += (_, _) => Save(false);
        overwrite.Click += (_, _) => Save(true);
        FormClosed += (_, _) => { password.Clear(); account.Clear(); };
        RefreshStatus();
        // No AcceptButton: an Enter key cannot silently submit or authorize this form.
    }

    private void RefreshStatus()
    {
        var current = service.Status(Policy.Reference);
        state.Text = !current.Success ? "无法安全确认凭据状态，禁止保存。" :
            current.Exists ? "已有凭据。仅点击“明确覆盖已有凭据”才能替换。" : "尚未保存此固定账号凭据。";
        save.Enabled = current.Success && !current.Exists;
        overwrite.Enabled = current.Success && current.Exists;
    }

    private void Save(bool allowOverwrite)
    {
        byte[]? accountBytes = null, passwordBytes = null;
        try
        {
            accountBytes = System.Text.Encoding.UTF8.GetBytes(account.Text);
            passwordBytes = System.Text.Encoding.UTF8.GetBytes(password.Text);
            // WinForms necessarily holds managed text while the human types. Clear controls early;
            // owned byte buffers are deterministically cleared, immutable temporary strings cannot be.
            password.Clear();
            var result = service.Save(Policy.Reference, accountBytes, passwordBytes, consent.Checked, allowOverwrite);
            Program.Print(result);
            if (result.Success) { account.Clear(); MessageBox.Show("已安全保存。自动重登许可：" + (result.AutomationAllowed ? "已勾选" : "未启用"), "完成"); Close(); }
            else { MessageBox.Show("未完成安全保存。请重新输入并检查状态；自动重登不会因失败启用。", "保存失败"); RefreshStatus(); }
        }
        catch { MessageBox.Show("未完成安全保存。请关闭窗口后重试。", "保存失败"); }
        finally { SecretMemory.Clear(accountBytes); SecretMemory.Clear(passwordBytes); password.Clear(); }
    }
}
