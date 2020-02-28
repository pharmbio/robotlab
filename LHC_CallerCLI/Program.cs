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

//
// This is a cli used to call the LHC Runner. The LHC Runner allows developers to
// run LHC protocol files to control an instrument. This Console App calls each of the 
// methods provided by the LHC Runner.
//
// Test run in PowerShell:
// 
// & "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe" "MultiFloFX" "USB MultiFloFX sn:19041612" LHC_TestCommunications
// & "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe" "405 TS/LS" "USB 405 TS/LS sn:191107F" LHC_TestCommunications
//
//

namespace LHCCallerCLI
{

	public class Response
	{
		public string status{ get; set; }
		public string value{ get; set; }
		public string details{ get; set; }

		public string toJson()
		{
			return "{" +
				    "\"status\": \"" + status + "\"" + "," +
				    "\"value\": \"" + value + "\"" + "," +
				    "\"details\": \"" + details + "\"" + 
					"}";
		}
	}

	public class Program
	{
		#region Data Declarations
	
		static ClassLHCRunner cLHC = new ClassLHCRunner();

		static String[] RUN_STATUS = new String[]{
				"0 - eUninitialized - should never be encountered",
				"1 - eReady - the run completed successfully: stop polling for status",
				"2 - eBusy - failed to run a new step: stop polling for status, the run has failed",
				"3 - eNotReady -  busy running current step: the run is still active, keep polling for further status",
				"4 - eError - this run has an error: stop polling for status, the run has failed. Call LHC_GetLastErrorCode to get the error code and then LHC_GetErrorString to get the error description",
				"5 - eDone - the current step is done, the next step will be started automatically: the run is still active, keep polling for further status",
				"6 - eIncomplete - (not used)",
				"7 - ePaused - the run is paused by user: the run is still active, keep polling for further status",
				"8 - eStopRequested - a Stop is requested by user: the run is still active, keep polling for further status",
				"9 - eStopping - the run is stopping per request: the run is still active, keep polling for further status",
				"10 - eNotRequired - (not used)"
				};

		static String[] RUNNER_RETURN_CODES = new String[]{
				"0 - eError",
				"1 - eOK",
				"2 - eRegistration_Failure",
				"3 - eInterface_Failure",
				"4 - eInvalid_Product_Type",
				"5 - eOpen_File_Error",
				"6 - ePre_Run_Error"
				};

		#endregion

		static void Main(string[] args)
		{

			try   
			{
				//Trace.Listeners.Add(new System.Diagnostics.ConsoleTraceListener());
				Trace.Listeners.Add(new TextWriterTraceListener("LHC_CallerCLI.log"));
				Trace.AutoFlush = true;
				
				runCommand(args);

			}
			catch(Exception e)
			{
				Console.WriteLine($"[Exception] {e}");	
			}
			finally
			{
            
			}
		}

		static void runCommand(string[] args)
		{

			Response response = new Response();

			try   
			{
				// Trace.TraceInformation("Start runCommand()");
           
				if (args.Length < 3)
				{
					printHelp();
					return;
				}

				string productName = args[0];
				//LHC_SetProductType(6);
				LHC_SetProductName(productName);

				string comString = args[1];
				LHC_SetCommunications(comString);

				string command = args[2];

				switch (command)
				{
					case "LHC_TestCommunications":
						short comStatus = LHC_TestCommunications();
						response.status = comStatus.ToString();
						response.details = getMessageFromReturnCode(comStatus);
						break;

					case "LHC_GetProductName":
						string prodName = LHC_GetProductName();
						response.status = "OK";
						response.value = prodName;
						break;

					case "LHC_GetProductSerialNumber":
						string serial = LHC_GetProductSerialNumber();
						response.status = "OK";
						response.value = serial;
						break;

					// OBS LHC_RunProtocol returns "3 - busy" when it starts running OK
					case "LHC_RunProtocol":
						string protocolFile = args[3];
						int runStatus = LHC_RunProtocol(protocolFile);
						response.status = runStatus.ToString();
						response.details = getRunMessageFromStatusCode(runStatus);
						break;

					case "LHC_GetProtocolStatus":
						int protocolStatus = LHC_GetProtocolStatus();
						response.status = protocolStatus.ToString();
						response.details = getRunMessageFromStatusCode(protocolStatus);
						break;

					// OBS LHC_RunVerifyManifoldTest returns "3 - busy" when it starts running OK
					case "LHC_RunVerifyManifoldTest":
						int runTestStatus = LHC_RunVerifyManifoldTest();
						response.status = runTestStatus.ToString();
						response.details = getRunMessageFromStatusCode(runTestStatus);
						break;

					case "LHC_GetVerifyManifoldRunStatus":
						int testStatus = LHC_GetVerifyManifoldRunStatus();
						response.status = testStatus.ToString();
						response.details = getRunMessageFromStatusCode(testStatus);
						break;

					case "LHC_GetVerifyManifoldTestResults":
						string testResults = LHC_GetVerifyManifoldTestResults();
						response.status = "OK";
						response.value = testResults;
						break;

//					case "LHC_PerformSelfCheck":
//						string testResults = LHC_PerformSelfCheck();
//						response.status = "OK";
//						response.value = testResults;
//						break;

					default:
						response.value = "WARNING";
						response.details = "No Command Specified";
						break;
				}
			}

			catch(Exception ex)
			{
				string value = "EXCEPTION";
				string errorString = "Message - {0} - " + 
									 "Source - {1} - " +
									 "StackTrace - {2} - " +
									 "TargetSite - {3} - ";
									 
				errorString = String.Format(errorString,
											ex.Message,
											ex.Source,
											ex.StackTrace,
				                            ex.TargetSite );

				response.status = "99";
				response.value = value;
				response.details = errorString;
			}

			Console.WriteLine(response.toJson());
		}

		static private void printHelp()
		{
			Console.WriteLine(	"Help:\n" + 
								"LHC_CallerCLI.exe <product> <com-port> <command> <parameters>\n" +
				                "\n" + 
								"Examples: \n" + 
								"LHC_CallerCLI.exe \"MultiFloFX\" \"USB MultiFloFX sn:19041612\" LHC_GetVerifyManifoldRunStatus\n" +
								"LHC_CallerCLI.exe \"MultiFloFX\" \"USB MultiFloFX sn:19041612\" LHC_RunProtocol \"c:\\protocols\\my-testprotocol\"\n" +
								"\n" + 
								"Some commands implemented:\n" +
								"LHC_TestCommunications\n" + 
								"LHC_GetProductName\n" + 
								"LHC_GetProductSerialNumber\n" + 
								"LHC_RunProtocol\n" + 
								"LHC_GetProtocolStatus\n" + 
								"LHC_RunVerifyManifoldTest\n" + 
								"LHC_GetVerifyManifoldRunStatus\n" + 
								"LHC_GetVerifyManifoldTestResults\n" + 
								"\n" + 
							    "Please check GitHub for more details."
							 );
		}

		static String getRunMessageFromStatusCode(int statusCode)
		{
			return RUN_STATUS[statusCode];
		}

		static String getMessageFromReturnCode(int returnCode)
		{
			return RUNNER_RETURN_CODES[returnCode];
		}	

		static private int LHC_RunProtocol(string protocolFile)
		{
			short nRetCode = cLHC.LHC_SetRunnerThreading(1);
			handleRetCodeErrors(nRetCode, "LHC_SetRunnerThreading");

			nRetCode = cLHC.LHC_LoadProtocolFromFile(protocolFile);
			handleRetCodeErrors(nRetCode, "LHC_LoadProtocolFromFile");

			// LHC_SetFirstStrip (); // optional call to set first strip to process (50 TS washer only)

			// LHC_SetNumberOfStrips (); // optional call to set number of strips to process (50 TS washer only)
		    
			// Trace.TraceInformation("Before validate");

			nRetCode = cLHC.LHC_ValidateProtocol(true); // optional call to force immediate validation
			handleRetCodeErrors(nRetCode, "LHC_ValidateProtocol");
		    
			// LHC_OverrideValidation(); // optional call to bypass validation

			// LHC_LeaveVacuumPumpOn(); // optional call to leave pump on when run is complete

			// int nRunStatus = cLHC.LHC_RunProtocol();
			// handleStatusCodeErrors(nRunStatus, "LHC_RunProtocol");

			// Trace.TraceInformation("Before start thread");

			Thread tRun = new Thread(ThreadRunProtocol);
			// Start running the protocol
			tRun.Start();

			// Trace.TraceInformation("After start thread");

			int nRunStatus = cLHC.LHC_GetProtocolStatus();

			// Trace.TraceInformation("nRunStatus=" + nRunStatus);


			return nRunStatus;
		}

		static void ThreadRunProtocol()
		{
			// This is the function that gets run in its own thread by the thread examples 1-3.

			// Start to run the protocol
			int nRunStatus = cLHC.LHC_RunProtocol();

			// Need to stay in the thread (this function) until the protocol is done otherwise
			// the protocol stops because the thread itself is gone once the function exits.
			int statusError = 4;
			int statusReady = 1;
			while ((nRunStatus != statusError) && (nRunStatus != statusReady))
			{
				nRunStatus = cLHC.LHC_GetProtocolStatus();
				// A sleep here will cause this thread only to sleep. The UI thread will still be active.
				Thread.Sleep(100);
			}

			// Done!

		}


		static private int LHC_RunVerifyManifoldTest()
		{
			short nRetCode = cLHC.LHC_SetRunnerThreading(1);
			handleRetCodeErrors(nRetCode, "LHC_SetRunnerThreading");

			int nRunStatus = cLHC.LHC_RunVerifyManifoldTest();
			handleStatusCodeErrors(nRunStatus, "LHC_RunProtocol");
			
			return nRunStatus;
		}

		static private string LHC_GetVerifyManifoldTestResults()
		{
			string testResult = cLHC.LHC_GetVerifyManifoldTestResults();
			return testResult;
		}		

		static private short LHC_SetProductName(string productName)
		{
			short nRetCode = cLHC.LHC_SetProductName(productName);
			handleRetCodeErrors(nRetCode, "Set Product Name");
			return nRetCode;
		}
		
		static private short LHC_SetProductType(short productType)
		{
			short nRetCode = cLHC.LHC_SetProductType(productType);
			handleRetCodeErrors(nRetCode, "LHC_SetProductType");
			return nRetCode;
		}

		static private short LHC_SetCommunications(string comPort)
		{
			short nRetCode = cLHC.LHC_SetCommunications(comPort);
			handleRetCodeErrors(nRetCode, "LHC_SetCommunications");
			return nRetCode;

		}
		static private short LHC_TestCommunications()
		{
			short nRetCode = cLHC.LHC_TestCommunications();
			handleRetCodeErrors(nRetCode, "LHC_TestCommunications");
			return nRetCode;
		} 
		static private string LHC_GetProductName()
		{
			string prodName = "na";
			short nRetCode = cLHC.LHC_GetProductName(ref prodName);
			handleRetCodeErrors(nRetCode, "LHC_GetProductName");
			return prodName;
		}
		static private string LHC_GetProductSerialNumber()
		{
			string serialNumber = "na";
			short nRetCode = cLHC.LHC_GetProductSerialNumber(ref serialNumber);
			handleRetCodeErrors(nRetCode, "LHC_GetProductSerialNumber");
			return serialNumber;
		}

		static private int LHC_GetProtocolStatus()
		{
			int statusCode = cLHC.LHC_GetProtocolStatus();
			handleStatusCodeErrors(statusCode, "LHC_GetProtocolStatus");
			return statusCode;
		}

		static private int LHC_GetVerifyManifoldRunStatus()
		{
			int statusCode = cLHC.LHC_GetVerifyManifoldRunStatus();
			handleStatusCodeErrors(statusCode, "LHC_GetVerifyManifoldRunStatus");
			return statusCode;
		}
		
		static void handleRetCodeErrors(short retCode, string calledMethod)
		{
			if (retCode != 1) // 1 = OK
			{
				string errorMessage = getLastError();		
				throw new Exception("Exception calling cLHC method: " + calledMethod + ", " + errorMessage);
			}
		}

		static void handleStatusCodeErrors(int statusCode, string calledMethod)
		{
			if (statusCode == 4) // 4 = Error
			{
				string errorMessage = getLastError();		
				throw new Exception("Exception calling cLHC method: " + calledMethod + ", " + errorMessage);
			}
		}

		static string getLastError()
		{
			short errorCode = cLHC.LHC_GetLastErrorCode();
			string errorString =  cLHC.LHC_GetErrorString(errorCode);
			string errorMessage = "ErrorCode: " + errorCode + ", ErrorString: " + errorString;
			return errorMessage;
		}

	}
}
