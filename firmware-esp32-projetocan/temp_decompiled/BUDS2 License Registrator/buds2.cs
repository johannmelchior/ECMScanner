using System;
using System.ComponentModel;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Management;
using System.Net;
using System.Net.Sockets;
using System.Runtime.CompilerServices;
using System.Text;
using System.Threading;
using System.Windows.Forms;
using BUDS2.Devices;
using BUDS2.My;
using Microsoft.VisualBasic;
using Microsoft.VisualBasic.CompilerServices;

namespace BUDS2
{
	// Token: 0x02000009 RID: 9
	[DesignerGenerated]
	public partial class buds2 : Form
	{
		// Token: 0x17000013 RID: 19
		// (get) Token: 0x0600002E RID: 46 RVA: 0x000028C1 File Offset: 0x00000AC1
		// (set) Token: 0x0600002F RID: 47 RVA: 0x000028C9 File Offset: 0x00000AC9
		private virtual BRP Adapter
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x06000030 RID: 48 RVA: 0x000028D2 File Offset: 0x00000AD2
		public buds2()
		{
			this.Adapter = new BRP();
			this.InitializeComponent();
			this.cmbLang.SelectedIndex = 0;
		}

		// Token: 0x06000031 RID: 49 RVA: 0x000028F8 File Offset: 0x00000AF8
		private void btnGetLicense_Click(object sender, EventArgs e)
		{
			if (this.txtEmail.Text.Length == 0)
			{
				Interaction.MsgBox("Input correct Email", MsgBoxStyle.OkOnly, null);
				return;
			}
			string serial;
			try
			{
				if (this.Adapter.State)
				{
					this.Adapter.Restart();
				}
				this.Adapter.Socket = 0;
				this.Adapter.Open();
				serial = this.Adapter.Serial;
				this.Adapter.Close();
			}
			catch (Exception ex)
			{
				Interaction.MsgBox("Error: MPI adapter no detected or VCI Driver not install", MsgBoxStyle.OkOnly, null);
				return;
			}
			string text = string.Format("{0},{1},{2},{3},{4},{5},{6},{7}", new object[]
			{
				this._GetHashCode(),
				serial,
				this.txtEmail.Text,
				this.txtName.Text,
				this.txtSurname.Text,
				this.txtCompany.Text,
				this.txtPhone.Text,
				this.cmbLang.SelectedItem.ToString()
			});
			int length = text.Length;
			TcpClient tcpClient = new TcpClient
			{
				NoDelay = true
			};
			bool flag = false;
			try
			{
				if (MyProject.Computer.Network.Ping("brptuning.com"))
				{
					tcpClient.Connect("brptuning.com", 9005);
					flag = tcpClient.Connected;
				}
			}
			catch (Exception ex2)
			{
			}
			if (!flag)
			{
				try
				{
					if (MyProject.Computer.Network.Ping("dius.brptuning.com"))
					{
						tcpClient.Connect("dius.brptuning.com", 9005);
					}
				}
				catch (Exception ex3)
				{
				}
			}
			if (!tcpClient.Connected)
			{
				Interaction.MsgBox("No connection to the license server", MsgBoxStyle.OkOnly, null);
				return;
			}
			checked
			{
				try
				{
					NetworkStream stream = tcpClient.GetStream();
					BinaryReader binaryReader = new BinaryReader(stream);
					BinaryWriter binaryWriter = new BinaryWriter(stream);
					binaryWriter.Write("BUDS2 License Client for DIUS platform");
					while (!stream.DataAvailable)
					{
						Thread.Sleep(50);
						this.$STATIC$btnGetLicense_Click$20211C12809D$Tick++;
						if (this.$STATIC$btnGetLicense_Click$20211C12809D$Tick > 100)
						{
							this.$STATIC$btnGetLicense_Click$20211C12809D$Tick = 0;
							Interaction.MsgBox("No connection to the license server", MsgBoxStyle.OkOnly, null);
							IL_035B:
							if (tcpClient.Connected)
							{
								binaryReader.Close();
								binaryReader.Dispose();
								binaryWriter.Close();
								binaryWriter.Dispose();
								stream.Close();
								stream.Dispose();
								tcpClient.Close();
							}
							return;
						}
					}
					if (stream.ReadByte() != 0)
					{
						Interaction.MsgBox("You are using an outdated version of the program. Install the new version", MsgBoxStyle.OkOnly, null);
						goto IL_035B;
					}
					binaryWriter.Write(text);
					byte b = binaryReader.ReadByte();
					if (b == 0)
					{
						int num = binaryReader.ReadInt32();
						string text2 = new string(binaryReader.ReadChars(num));
						DirectoryInfo directoryInfo = new DirectoryInfo(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) + "\\in2soft_license");
						if (directoryInfo.Exists)
						{
							directoryInfo = new DirectoryInfo(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) + "\\in2soft_license\\1225765425");
							if (!directoryInfo.Exists)
							{
								directoryInfo.Create();
							}
						}
						else
						{
							directoryInfo.Create();
							directoryInfo.CreateSubdirectory("1225765425");
						}
						FileStream fileStream = new FileStream(Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) + "\\in2soft_license\\1225765425\\license_" + this.txtEmail.Text + ".xml.bin", FileMode.Create);
						BinaryWriter binaryWriter2 = new BinaryWriter(fileStream);
						binaryWriter2.Write(Encoding.ASCII.GetBytes(text2));
						binaryWriter2.Close();
						fileStream.Close();
						tcpClient.Close();
						binaryReader.Close();
						binaryWriter.Close();
						Interaction.MsgBox("License store in " + Environment.GetFolderPath(Environment.SpecialFolder.UserProfile) + "\\in2soft_license\\1225765425 Folder", MsgBoxStyle.OkOnly, null);
						base.Close();
						goto IL_035B;
					}
					if (b != 130)
					{
						goto IL_035B;
					}
					Interaction.MsgBox("No have License for this Email or Serial Adapter", MsgBoxStyle.OkOnly, null);
					goto IL_035B;
				}
				catch (Exception ex4)
				{
					Interaction.MsgBox("No connection to the license server", MsgBoxStyle.OkOnly, null);
				}
			}
		}

		// Token: 0x06000032 RID: 50 RVA: 0x00002D1C File Offset: 0x00000F1C
		private string _GetHashCode()
		{
			string text = "";
			SelectQuery selectQuery = new SelectQuery("Win32_BIOS");
			ManagementObjectSearcher managementObjectSearcher = new ManagementObjectSearcher(selectQuery);
			try
			{
				foreach (ManagementBaseObject managementBaseObject in managementObjectSearcher.Get())
				{
					ManagementObject managementObject = (ManagementObject)managementBaseObject;
					text += managementObject["SerialNumber"].ToString();
				}
			}
			finally
			{
				ManagementObjectCollection.ManagementObjectEnumerator enumerator;
				if (enumerator != null)
				{
					((IDisposable)enumerator).Dispose();
				}
			}
			selectQuery = new SelectQuery("Win32_Processor");
			managementObjectSearcher = new ManagementObjectSearcher(selectQuery);
			try
			{
				foreach (ManagementBaseObject managementBaseObject2 in managementObjectSearcher.Get())
				{
					ManagementObject managementObject = (ManagementObject)managementBaseObject2;
					text += managementObject["ProcessorID"].ToString();
				}
			}
			finally
			{
				ManagementObjectCollection.ManagementObjectEnumerator enumerator2;
				if (enumerator2 != null)
				{
					((IDisposable)enumerator2).Dispose();
				}
			}
			text += Dns.GetHostName();
			selectQuery = new SelectQuery("Win32_BaseBoard");
			managementObjectSearcher = new ManagementObjectSearcher(selectQuery);
			try
			{
				foreach (ManagementBaseObject managementBaseObject3 in managementObjectSearcher.Get())
				{
					ManagementObject managementObject = (ManagementObject)managementBaseObject3;
					text += managementObject["SerialNumber"].ToString();
				}
			}
			finally
			{
				ManagementObjectCollection.ManagementObjectEnumerator enumerator3;
				if (enumerator3 != null)
				{
					((IDisposable)enumerator3).Dispose();
				}
			}
			return text;
		}

		// Token: 0x17000014 RID: 20
		// (get) Token: 0x06000035 RID: 53 RVA: 0x00003597 File Offset: 0x00001797
		// (set) Token: 0x06000036 RID: 54 RVA: 0x0000359F File Offset: 0x0000179F
		internal virtual Label lblEmail
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x17000015 RID: 21
		// (get) Token: 0x06000037 RID: 55 RVA: 0x000035A8 File Offset: 0x000017A8
		// (set) Token: 0x06000038 RID: 56 RVA: 0x000035B0 File Offset: 0x000017B0
		internal virtual TextBox txtName
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x17000016 RID: 22
		// (get) Token: 0x06000039 RID: 57 RVA: 0x000035B9 File Offset: 0x000017B9
		// (set) Token: 0x0600003A RID: 58 RVA: 0x000035C1 File Offset: 0x000017C1
		internal virtual Label lblName
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x17000017 RID: 23
		// (get) Token: 0x0600003B RID: 59 RVA: 0x000035CA File Offset: 0x000017CA
		// (set) Token: 0x0600003C RID: 60 RVA: 0x000035D2 File Offset: 0x000017D2
		internal virtual TextBox txtSurname
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x17000018 RID: 24
		// (get) Token: 0x0600003D RID: 61 RVA: 0x000035DB File Offset: 0x000017DB
		// (set) Token: 0x0600003E RID: 62 RVA: 0x000035E3 File Offset: 0x000017E3
		internal virtual Label lblSurname
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x17000019 RID: 25
		// (get) Token: 0x0600003F RID: 63 RVA: 0x000035EC File Offset: 0x000017EC
		// (set) Token: 0x06000040 RID: 64 RVA: 0x000035F4 File Offset: 0x000017F4
		internal virtual TextBox txtCompany
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x1700001A RID: 26
		// (get) Token: 0x06000041 RID: 65 RVA: 0x000035FD File Offset: 0x000017FD
		// (set) Token: 0x06000042 RID: 66 RVA: 0x00003605 File Offset: 0x00001805
		internal virtual Label lblCompany
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x1700001B RID: 27
		// (get) Token: 0x06000043 RID: 67 RVA: 0x0000360E File Offset: 0x0000180E
		// (set) Token: 0x06000044 RID: 68 RVA: 0x00003616 File Offset: 0x00001816
		internal virtual TextBox txtPhone
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x1700001C RID: 28
		// (get) Token: 0x06000045 RID: 69 RVA: 0x0000361F File Offset: 0x0000181F
		// (set) Token: 0x06000046 RID: 70 RVA: 0x00003627 File Offset: 0x00001827
		internal virtual Label lblPhone
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x1700001D RID: 29
		// (get) Token: 0x06000047 RID: 71 RVA: 0x00003630 File Offset: 0x00001830
		// (set) Token: 0x06000048 RID: 72 RVA: 0x00003638 File Offset: 0x00001838
		internal virtual Button btnGetLicense
		{
			[CompilerGenerated]
			get
			{
				return this._btnGetLicense;
			}
			[CompilerGenerated]
			[MethodImpl(MethodImplOptions.Synchronized)]
			set
			{
				EventHandler eventHandler = new EventHandler(this.btnGetLicense_Click);
				Button button = this._btnGetLicense;
				if (button != null)
				{
					button.Click -= eventHandler;
				}
				this._btnGetLicense = value;
				button = this._btnGetLicense;
				if (button != null)
				{
					button.Click += eventHandler;
				}
			}
		}

		// Token: 0x1700001E RID: 30
		// (get) Token: 0x06000049 RID: 73 RVA: 0x0000367B File Offset: 0x0000187B
		// (set) Token: 0x0600004A RID: 74 RVA: 0x00003683 File Offset: 0x00001883
		internal virtual TextBox txtEmail
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x1700001F RID: 31
		// (get) Token: 0x0600004B RID: 75 RVA: 0x0000368C File Offset: 0x0000188C
		// (set) Token: 0x0600004C RID: 76 RVA: 0x00003694 File Offset: 0x00001894
		internal virtual ComboBox cmbLang
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x17000020 RID: 32
		// (get) Token: 0x0600004D RID: 77 RVA: 0x0000369D File Offset: 0x0000189D
		// (set) Token: 0x0600004E RID: 78 RVA: 0x000036A5 File Offset: 0x000018A5
		internal virtual Label Label1
		{
			get; [MethodImpl(MethodImplOptions.Synchronized)]
			set;
		}

		// Token: 0x0400002B RID: 43
		private int $STATIC$btnGetLicense_Click$20211C12809D$Tick;

		// Token: 0x0200000E RID: 14
		public enum Err : byte
		{
			// Token: 0x04000030 RID: 48
			OK,
			// Token: 0x04000031 RID: 49
			NewDevice = 128,
			// Token: 0x04000032 RID: 50
			NoInfo,
			// Token: 0x04000033 RID: 51
			NoAccess,
			// Token: 0x04000034 RID: 52
			Incorrect,
			// Token: 0x04000035 RID: 53
			Err = 255
		}
	}
}
