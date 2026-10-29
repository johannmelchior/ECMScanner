using System;
using System.Collections;
using System.ComponentModel;
using System.Threading;
using System.Windows.Forms;
using Ixxat.Vci3;
using Ixxat.Vci3.Bal;
using Ixxat.Vci3.Bal.Can;
using Microsoft.VisualBasic;
using Microsoft.VisualBasic.CompilerServices;

namespace BUDS2.Devices
{
	// Token: 0x02000008 RID: 8
	public class BRP : Component
	{
		// Token: 0x06000014 RID: 20 RVA: 0x0000221C File Offset: 0x0000041C
		public BRP()
		{
			this.mSocket = 0;
			this.mFilter = 0U;
			this.mMask = 0U;
			this.mBitRate = CanBitrate.Cia250KBit;
		}

		// Token: 0x14000001 RID: 1
		// (add) Token: 0x06000015 RID: 21 RVA: 0x00002244 File Offset: 0x00000444
		// (remove) Token: 0x06000016 RID: 22 RVA: 0x0000227C File Offset: 0x0000047C
		public event BRP.MsgCANEventHandler MsgCAN;

		// Token: 0x06000017 RID: 23 RVA: 0x000022B4 File Offset: 0x000004B4
		private bool SelectDevice()
		{
			bool flag;
			try
			{
				IVciDeviceManager deviceManager = VciServer.GetDeviceManager();
				IVciDeviceList deviceList = deviceManager.GetDeviceList();
				IEnumerator enumerator = deviceList.GetEnumerator();
				enumerator.MoveNext();
				BRP.mDevice = (IVciDevice)enumerator.Current;
			}
			catch (Exception ex)
			{
				flag = true;
			}
			finally
			{
				IVciDeviceManager deviceManager;
				BRP.DisposeVciObject(deviceManager);
				IVciDeviceList deviceList;
				BRP.DisposeVciObject(deviceList);
				IEnumerator enumerator;
				BRP.DisposeVciObject(enumerator);
			}
			return flag;
		}

		// Token: 0x06000018 RID: 24 RVA: 0x00002330 File Offset: 0x00000530
		private bool InitSocket()
		{
			IBalObject balObject = null;
			checked
			{
				bool flag;
				try
				{
					balObject = BRP.mDevice.OpenBusAccessLayer();
					BRP.mCanChn = (ICanChannel)balObject.OpenSocket((byte)this.mSocket, typeof(ICanChannel));
					BRP.mCanChn.Initialize(1024, 128, false);
					BRP.mReader = BRP.mCanChn.GetMessageReader();
					BRP.mReader.Threshold = 1;
					BRP.mRxEvent = new AutoResetEvent(false);
					BRP.mReader.AssignEvent(BRP.mRxEvent);
					BRP.mWriter = BRP.mCanChn.GetMessageWriter();
					BRP.mWriter.Threshold = 1;
					BRP.mCanChn.Activate();
					BRP.mCanCtl = (ICanControl)balObject.OpenSocket((byte)this.mSocket, typeof(ICanControl));
					BRP.mCanCtl.InitLine(CanOperatingModes.Standard, this.mBitRate);
					BRP.mCanCtl.SetAccFilter(CanFilter.Std, this.mFilter, this.mMask);
					BRP.mCanCtl.StartLine();
				}
				catch (Exception ex)
				{
					flag = true;
				}
				finally
				{
					BRP.DisposeVciObject(balObject);
				}
				return flag;
			}
		}

		// Token: 0x06000019 RID: 25 RVA: 0x00002464 File Offset: 0x00000664
		public static void Write(CanMessage CanMsg)
		{
			try
			{
				BRP.mWriter.SendMessage(CanMsg);
			}
			catch (Exception ex)
			{
				Console.Write("\nerror");
			}
		}

		// Token: 0x0600001A RID: 26 RVA: 0x000024A8 File Offset: 0x000006A8
		public void ReceiveThreadFunc()
		{
			do
			{
				CanMessage canMessage;
				if (BRP.mRxEvent.WaitOne(20, false) && BRP.mReader.ReadMessage(out canMessage))
				{
					switch (canMessage.FrameType)
					{
					case CanMsgFrameType.Data:
						if (!canMessage.RemoteTransmissionRequest && canMessage.Identifier == this.mReceiver)
						{
							this.mMessage = canMessage;
							this.mInData = true;
							Application.DoEvents();
							Thread.Sleep(20);
						}
						break;
					case CanMsgFrameType.Info:
						switch (canMessage[0])
						{
						case 1:
							Console.Write("\nCAN started...");
							break;
						case 2:
							Console.Write("\nCAN stopped...");
							break;
						case 3:
							Console.Write("\nCAN reseted...");
							break;
						}
						break;
					case CanMsgFrameType.Error:
						switch (canMessage[0])
						{
						case 1:
							Console.Write("\nstuff error...");
							break;
						case 2:
							Console.Write("\nform error...");
							break;
						case 3:
							Console.Write("\nacknowledgment error...");
							break;
						case 4:
							Console.Write("\nbit error...");
							break;
						case 6:
							Console.Write("\nCRC error...");
							break;
						case 7:
							Console.Write("\nother error...");
							break;
						}
						break;
					}
				}
			}
			while (BRP.mMustQuit == 0L);
		}

		// Token: 0x0600001B RID: 27 RVA: 0x00002600 File Offset: 0x00000800
		public void Open()
		{
			if (this.SelectDevice())
			{
				throw new ApplicationException("No Find Device");
			}
			this.InitSocket();
			this.mState = true;
			BRP.rxThread = new Thread(new ThreadStart(this.ReceiveThreadFunc));
			BRP.rxThread.Start();
		}

		// Token: 0x0600001C RID: 28 RVA: 0x0000264E File Offset: 0x0000084E
		public void Close()
		{
			this.mState = false;
			Interlocked.Exchange(ref BRP.mMustQuit, 1L);
			BRP.rxThread.Join();
			BRP.FinalizeApp();
		}

		// Token: 0x0600001D RID: 29 RVA: 0x00002674 File Offset: 0x00000874
		public void Restart()
		{
			this.mState = false;
			try
			{
				BRP.mCanCtl.StopLine();
			}
			catch (Exception ex)
			{
				return;
			}
			BRP.mCanCtl.InitLine(CanOperatingModes.Standard, this.mBitRate);
			BRP.mCanCtl.SetAccFilter(CanFilter.Std, this.mFilter, this.mMask);
			BRP.mCanCtl.StartLine();
			this.mState = true;
		}

		// Token: 0x0600001E RID: 30 RVA: 0x000026EC File Offset: 0x000008EC
		private static void FinalizeApp()
		{
			BRP.DisposeVciObject(BRP.mReader);
			BRP.DisposeVciObject(BRP.mWriter);
			BRP.DisposeVciObject(BRP.mCanChn);
			BRP.DisposeVciObject(BRP.mCanCtl);
			BRP.DisposeVciObject(BRP.mDevice);
		}

		// Token: 0x0600001F RID: 31 RVA: 0x00002720 File Offset: 0x00000920
		private static void DisposeVciObject(object obj)
		{
			if (obj != null)
			{
				IDisposable disposable = obj as IDisposable;
				if (disposable != null)
				{
					disposable.Dispose();
					obj = null;
				}
			}
		}

		// Token: 0x1700000A RID: 10
		// (get) Token: 0x06000020 RID: 32 RVA: 0x00002744 File Offset: 0x00000944
		// (set) Token: 0x06000021 RID: 33 RVA: 0x00002759 File Offset: 0x00000959
		public int Socket
		{
			get
			{
				return this.mSocket;
			}
			set
			{
				this.mSocket = value;
			}
		}

		// Token: 0x1700000B RID: 11
		// (get) Token: 0x06000022 RID: 34 RVA: 0x00002764 File Offset: 0x00000964
		// (set) Token: 0x06000023 RID: 35 RVA: 0x00002779 File Offset: 0x00000979
		public uint Filter
		{
			get
			{
				return this.mFilter;
			}
			set
			{
				this.mFilter = value;
			}
		}

		// Token: 0x1700000C RID: 12
		// (get) Token: 0x06000024 RID: 36 RVA: 0x00002784 File Offset: 0x00000984
		// (set) Token: 0x06000025 RID: 37 RVA: 0x00002799 File Offset: 0x00000999
		public uint Mask
		{
			get
			{
				return this.mMask;
			}
			set
			{
				this.mMask = value;
			}
		}

		// Token: 0x1700000D RID: 13
		// (get) Token: 0x06000026 RID: 38 RVA: 0x000027A4 File Offset: 0x000009A4
		// (set) Token: 0x06000027 RID: 39 RVA: 0x000027B9 File Offset: 0x000009B9
		public CanBitrate BitRate
		{
			get
			{
				return this.mBitRate;
			}
			set
			{
				this.mBitRate = value;
			}
		}

		// Token: 0x1700000E RID: 14
		// (get) Token: 0x06000028 RID: 40 RVA: 0x000027C4 File Offset: 0x000009C4
		public bool State
		{
			get
			{
				return this.mState;
			}
		}

		// Token: 0x1700000F RID: 15
		// (get) Token: 0x06000029 RID: 41 RVA: 0x000027DC File Offset: 0x000009DC
		public string Serial
		{
			get
			{
				checked
				{
					string text;
					if (Operators.CompareString(BRP.mDevice.UniqueHardwareId.GetType().ToString(), "System.String", false) == 0)
					{
						text = Conversions.ToString(BRP.mDevice.UniqueHardwareId);
					}
					else
					{
						text = "";
						object uniqueHardwareId = BRP.mDevice.UniqueHardwareId;
						byte[] array = ((uniqueHardwareId != null) ? ((Guid)uniqueHardwareId) : default(Guid)).ToByteArray();
						uint num = 0U;
						do
						{
							text += Conversions.ToString(Strings.Chr((int)array[(int)num]));
							num += 1U;
						}
						while (num <= 8U);
					}
					return text;
				}
			}
		}

		// Token: 0x17000010 RID: 16
		// (get) Token: 0x0600002A RID: 42 RVA: 0x00002870 File Offset: 0x00000A70
		// (set) Token: 0x0600002B RID: 43 RVA: 0x00002885 File Offset: 0x00000A85
		public uint Receiver
		{
			get
			{
				return this.mReceiver;
			}
			set
			{
				this.mReceiver = value;
			}
		}

		// Token: 0x17000011 RID: 17
		// (get) Token: 0x0600002C RID: 44 RVA: 0x00002890 File Offset: 0x00000A90
		public bool InData
		{
			get
			{
				bool flag = this.mInData;
				this.mInData = false;
				return flag;
			}
		}

		// Token: 0x17000012 RID: 18
		// (get) Token: 0x0600002D RID: 45 RVA: 0x000028AC File Offset: 0x00000AAC
		public CanMessage Message
		{
			get
			{
				return this.mMessage;
			}
		}

		// Token: 0x0400000C RID: 12
		private static IVciDevice mDevice;

		// Token: 0x0400000D RID: 13
		private static ICanControl mCanCtl;

		// Token: 0x0400000E RID: 14
		private static ICanChannel mCanChn;

		// Token: 0x0400000F RID: 15
		private static ICanMessageWriter mWriter;

		// Token: 0x04000010 RID: 16
		private static ICanMessageReader mReader;

		// Token: 0x04000011 RID: 17
		private static Thread rxThread;

		// Token: 0x04000012 RID: 18
		private static long mMustQuit = 0L;

		// Token: 0x04000013 RID: 19
		private static AutoResetEvent mRxEvent;

		// Token: 0x04000014 RID: 20
		private int mSocket;

		// Token: 0x04000015 RID: 21
		private uint mFilter;

		// Token: 0x04000016 RID: 22
		private uint mMask;

		// Token: 0x04000017 RID: 23
		private CanBitrate mBitRate;

		// Token: 0x04000018 RID: 24
		private bool mState;

		// Token: 0x04000019 RID: 25
		private uint mReceiver;

		// Token: 0x0400001A RID: 26
		private bool mInData;

		// Token: 0x0400001B RID: 27
		private CanMessage mMessage;

		// Token: 0x0200000D RID: 13
		// (Invoke) Token: 0x06000064 RID: 100
		public delegate void MsgCANEventHandler(CanMessage Message);
	}
}
