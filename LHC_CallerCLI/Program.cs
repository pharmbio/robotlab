using System;
using System.Collections.Generic;
using System.ComponentModel;
using System.Data;
using System.Text;
using System.Media;
using System.Reflection;
using System.IO;
using System.Threading;

using BTILHCRunner;
using System.Diagnostics;

// This is a cli used to call the LHC Runner. The LHC Runner allows developers to
// run LHC protocol files to control an instrument. This Console App calls each of the 
// methods provided by the LHC Runner.

namespace LHCCallerCLI
{
	public class Program
	{

		static void Main(string[] args)
		{


			//runCommand(args);
			try   
			{
				Console.WriteLine("Start Main()");
				Debug.WriteLine("This is sent to debug output.");
				LHC_SetProductName("MultiFloFX");
				LHC_SetCommunications("USB MultiFloFX sn:19041612");
				//LHC_SetCommunications("USB 405 TS/LS sn:191107F");

				string name = LHC_GetProductName();
				Console.WriteLine("prodName:" + name);

				string serialNumber = LHC_GetProductSerialNumber();
				Console.WriteLine("serialNumber:" + serialNumber);

				LHC_TestCommunications();
				Console.WriteLine("Done Main()");

			}
			catch(Exception e)
			{
				Console.WriteLine($"[Exception] {e}");
            
				// Set exception in return object
		
			}
			finally
			{
            
			}
		}

		static void runCommand(string[] args)
		{

			try   
			{
           
				if (args.Length < 3)
				{
					printHelp();
					return;
				}

				string productName = args[0];
				LHC_SetProductName(productName);

				string comString = args[1];
				LHC_SetCommunications(comString);

				string command = args[2];

				switch (command)
				{

					case "LHC_TestCommunications":
						LHC_TestCommunications();
						break;

					case "LHC_GetProductName":
						LHC_GetProductName();
						break;

					case "LHC_GetProductSerialNumber":
						LHC_GetProductSerialNumber();
						break;

					default:
						Console.WriteLine("Nothing");
						break;
				}

			}
			catch(Exception e)
			{
				Console.WriteLine($"[Exception] {e}");
            
				// Set exception in return object
		
			}
			finally
			{
            
			}

		}

		static private void printHelp()
		{
			Console.WriteLine("Could not parse command line...");
		}


/*
 
		4.1. Product Initialization
		LHC_SetProductName();
		LHC_SetCommunications();
		// set product name: El406, ELx405, MultiFloFX, etc...
		// set COM port to use or indicate direct USB

		4.2. Communications Test
		Perform Product Initialization sequence
		LHC_TestCommunications()
		// test that device is attached and responding


		Running Protocols from .LHC File
		LHC_LoadProtocolFromFile(); // file and pathname of LHC protocol
		LHC_SetCommunications(); // set COM port to use or indicate direct USB
		LHC_TestCommunications(); // confirm instrument attached is responding
		LHC_SetFirstStrip (); // optional call to set first strip to process (50 TS washer only)
		LHC_SetNumberOfStrips (); // optional call to set number of strips to process (50 TS washer only)
		LHC_ValidateProtocol(); // optional call to force immediate validation
		LHC_OverrideValidation(); // optional call to bypass validation
		LHC_LeaveVacuumPumpOn(); // optional call to leave pump on when run is complete
		LHC_RunProtocol();

		// validates protocol to instrument and starts execution
		While LHC Protocol not complete {
			LHC_GetProtocolStatus()
			// return completion status of executing LHC protocol file
			Optional
			LHC_PauseProtocol()
			If paused
			LHC_ResumeProtocol() or
			LHC_AbortProtocol()
		}
		If error generated
		LHC_GetErrorString()
*/
		static private void LHC_SetProductName(string productName)
		{
			short nRetCode = (cLHC.LHC_SetProductName(productName));
			handleRetCode(nRetCode, "Set Product Name");
		}

		// The following method is outdated and should not be used.  Although it is 
		// still enabled, it is not the recommended approach for selecting the 
		//  instrumenttype be cause it does not allow for foreward compatibility.
		static private void LHC_SetProductType(string productType)
		{
			short shortProdType = Convert.ToInt16(productType);
			short nRetCode = cLHC.LHC_SetProductType(shortProdType);
			handleRetCode(nRetCode, "Set Product Type");

		} 
		static private void LHC_SetCommunications(string comPort)
		{
			short nRetCode = (cLHC.LHC_SetCommunications(comPort));
			handleRetCode(nRetCode, "Set Communications");
		}
		static private void LHC_TestCommunications()
		{
			short nRetCode = cLHC.LHC_TestCommunications();
			handleRetCode(nRetCode, "Test Port");
		} 
		static private string LHC_GetProductName()
		{
			string prodName = "na";
			short nRetCode = cLHC.LHC_GetProductName(ref prodName);
			/*
			if (strName == "")
			{
				labelProductName.Text = "Not Read";
				textBoxErrorString.Text += "Failed";
			}
			else
			{
				labelProductName.Text = strName;
				textBoxErrorString.Text += "Successful";
			}
			*/
			handleRetCode(nRetCode, "Get Product Name");
			return prodName;
		}
		static private string LHC_GetProductSerialNumber()
		{
			string serialNumber = "na";
			short nRetCode = cLHC.LHC_GetProductSerialNumber(ref serialNumber);
			/*
			if (strSN == "")
			{
				labelSerialNumber.Text = "Not Read";
				textBoxErrorString.Text += "Failed";
			}
			else
			{
				labelSerialNumber.Text = strSN;
				textBoxErrorString.Text += "Successful";
			}
			*/
			handleRetCode(nRetCode, "Get Product SN");
			return serialNumber;
		}


		static void handleRetCode(short retCode, string calledMethod)
		{

			if (retCode == BTI_OK)
			{
				Console.WriteLine(calledMethod + " - Successful");
			}
			else
			{
				short errorCode = cLHC.LHC_GetLastErrorCode();
				string errorString =  cLHC.LHC_GetErrorString(errorCode);
				string errorMessage = "Exception calling LHC method: " + calledMethod + ", ErrorCode: " + errorCode + ", ErrorString: " + errorString;
				// Console.WriteLine(errorMessage);
				throw new Exception(errorMessage);
			}

		}

		#region Data Declarations 
		// Instrument products
		public enum enumProductType
		{
			eUndefined = 0,
			eEL406 = 1,
			eELx405 = 2,
			eMicroFlo = 3,
			eMultiFlo = 4,
			e405TS = 5,
			eMultiFloFX = 6
		}
		// Instrument status
		public enum enumRunStatus
		{
			eUninitialized,
			eReady,
			eNotReady,
			eBusy,
			eError,
			eDone,
			eIncomplete,
			ePaused,
			eStopRequested,
			eStopping,
			eNotRequired
		}

		// Used to send messages in timer handler if user presses Pause,
		// Resume, or Abort keys
		public enum enumSendMsgType
		{
			eSendPauseMsg,
			eSendResumeMsg,
			eSendAbortMsg,
			eSendGetStatusMsg
		}
		public enumSendMsgType eSendMsgType = enumSendMsgType.eSendGetStatusMsg;
		public Boolean bTimerRunning = false;

		public const Int16 BTI_OK = 1;
		public Int16 nTimerTickCount = 0;
		public Int16 nRunCount = 1;
		bool bTimerTickBusy = false;
		DateTime dtTimeStamp;
		//	int nTimeStampCount;

		// New for threading tests - KRB 4/20/2012
		static enumRunStatus eRunStatus;
		// Examples of static variables that can be read by the UI thread and the thread that runs the protocol
		//static string strComPort;
		//static string strProtocolToRun;

		static string strRunTimeErrorString;
		static EventWaitHandle _done = new AutoResetEvent(false);
		static BackgroundWorker RunProtocolThread;
		static int nThreadExperimentType;

		// thread experiment 4
		// delegate used to launch worker function
		public delegate void workerFunctionDelegate(ThreadParams p_clThreadParams);
		// delegate to display results
		public delegate void updateStatusDisplayDelegate(enumRunStatus p_eStatus, string strResult);

		public class ThreadParams
		{
			public ClassLHCRunner cLHC;
			public enumRunStatus eRunStatus;
			public string strRunTimeErrorString;
		}

		// Each form has its own structure containing the runner and the status variable
		ThreadParams clThreadParams = new ThreadParams();

		static ClassLHCRunner cLHC = new ClassLHCRunner();
		#endregion


	}
}
