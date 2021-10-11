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
        static String getRunMessageFromStatusCode(int statusCode)
        {
            return RUN_STATUS[statusCode];
        }

        static String getMessageFromReturnCode(int returnCode)
        {
            return RUNNER_RETURN_CODES[returnCode];
        }

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

        /*

            Example test calls (from powerscript):

                & "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe" "405 TS/LS" "USB 405 TS/LS sn:191107F"
                & "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe" "405 TS/LS" "USB 405 TS/LS sn:191107F" "C:\ProgramData\BioTek\Liquid Handling Control 2.22\Protocols\"
                & "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe" "MultiFloFX" "USB MultiFloFX sn:19041612"
                & "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe" "MultiFloFX" "USB MultiFloFX sn:19041612" "C:\ProgramData\BioTek\Liquid Handling Control 2.22\Protocols\"

        */
        static void Main(string[] args)
        {
            try {
                if (args.Length < 2) {
                    printHelp();
                    return;
                }

                LHC_SetProductName(args[0]);
                LHC_SetCommunications(args[1]);

                string path_prefix = ""
                if (args.Length == 3) {
                    path_prefix = args[2]
                }
                Loop(path_prefix);
            } catch (Exception e) {
                Console.WriteLine($"[Exception] {e}");
            }
        }

        static void Loop(string path_prefix)
        {
            string last_validated_protocol = " ";
            while (true) {
                Console.WriteLine("ready");
                string line = Console.ReadLine().Trim();
                string[] parts = line.split(' ');
                string cmd = "";
                string arg = "";
                if (parts.Length == 1) {
                    cmd = parts[0];
                } else if (parts.Length == 2) {
                    cmd = parts[0];
                    arg = parts[1];
                } else if (parts.Length > 2) {
                    Console.WriteLine("error too many arguments");
                    continue;
                }
                try {
                    HandleMessage(cmd, arg, path_prefix, out last_validated_protocol);
                } catch (Exception e) {
                    Console.WriteLine($"error {e}");
                }
            }
        }

        static void HandleMessage(string cmd, string arg, string path_prefix, out string last_validated_protocol)
        {
            if (cmd == "TestCommunications") {
                short runnerCode = LHC_TestCommunications();
                string details = getMessageFromReturnCode(status);
                Console.WriteLine("status", status);
                Console.WriteLine("message", details);
            } else if (cmd == "RunProtocol") {
                if (arg == "") {
                    Console.WriteLine("error protocol name argument required");
                    continue;
                }
                last_validated_protocol = " ";
                RunProtocol(arg);
                Console.WriteLine("success");
            } else if (cmd == "ValidateProtocol") {
                if (arg == "") {
                    Console.WriteLine("error protocol name argument required");
                    continue;
                }
                last_validated_protocol = " ";
                ValidateProtocol(arg);
                last_validated_protocol = arg;
                Console.WriteLine("success");
            } else if (cmd == "RunLastValidatedProtocol") {
                if (arg == "") {
                    Console.WriteLine("error protocol name argument required");
                    continue;
                }
                if (last_validated_protocol != arg) {
                    Console.WriteLine("error last validated protocol and argument does not match");
                    continue;
                }
                string protocolFile = args[3];
                RunLastValidatedProtocol();
                Console.WriteLine("success");
            } else {
                Console.WriteLine("error unknown command");
            }
        }

        static private void RunProtocol(string protocolFile)
        {
            ValidateProtocol(protocolFile);
            RunLastValidatedProtocol();
        }

        static private void ValidateProtocol(string protocolFile)
        {
            Console.WriteLine("message validation begin");
            short nRetCode = cLHC.LHC_SetRunnerThreading(1);
            handleRetCodeErrors(nRetCode, "LHC_SetRunnerThreading");

            nRetCode = cLHC.LHC_LoadProtocolFromFile(protocolFile);
            handleRetCodeErrors(nRetCode, "LHC_LoadProtocolFromFile");

            nRetCode = cLHC.LHC_ValidateProtocol(true);
            handleRetCodeErrors(nRetCode, "LHC_ValidateProtocol");

            nRetCode = LHC_OverrideValidation(1);
            handleRetCodeErrors(nRetCode, "LHC_OverrideValidation");
            Console.WriteLine("message validation done");
        }

        static private void RunLastValidatedProtocol(string protocolFile)
        {
            Console.WriteLine("message protocol begin");
            Thread tRun = new Thread(ThreadRunProtocol);
            tRun.Start();
            tRun.Join();
            Console.WriteLine("message protocol done");
            short status = cLHC.LHC_GetProtocolStatus()
            Console.WriteLine("status", status);
            handleStatusCodeErrors(status, "RunLastValidatedProtocol");
            string details = getMessageFromReturnCode(status);
            Console.WriteLine("message", details);
        }

        static void ThreadRunProtocol()
        {
            // Start to run the protocol
            int nRunStatus = cLHC.LHC_RunProtocol();

            // Need to stay in the thread (this function) until the protocol is done otherwise
            // the protocol stops because the thread itself is gone once the function exits.
            int statusError = 4;
            int statusReady = 1;
            while ((nRunStatus != statusError) && (nRunStatus != statusReady)) {
                nRunStatus = cLHC.LHC_GetProtocolStatus();
                // A sleep here will cause this thread only to sleep. The UI thread will still be active.
                Thread.Sleep(100);
            }
            // Done!
        }

        static private short LHC_SetCommunications(string comPort)
        {
            short nRetCode = cLHC.LHC_SetCommunications(comPort);
            handleRetCodeErrors(nRetCode, "LHC_SetCommunications");
            return nRetCode;

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

        static private short LHC_TestCommunications()
        {
            short nRetCode = cLHC.LHC_TestCommunications();
            handleRetCodeErrors(nRetCode, "LHC_TestCommunications");
            return nRetCode;
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
                Console.WriteLine("message", errorMessage);
                throw new Exception("Exception calling cLHC method: " + calledMethod + ", " + errorMessage);
            }
        }

        static void handleStatusCodeErrors(int statusCode, string calledMethod)
        {
            if (statusCode == 4) // 4 = Error
            {
                string errorMessage = getLastError();
                Console.WriteLine("message", errorMessage);
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

        static private void printHelp()
        {
            Console.WriteLine(
                "Help:\n" +
                "\tLHC_CallerCLI.exe <product> <com-port> [path-prefix]\n" +
                "\n" +
                "Examples: \n" +
                "\tLHC_CallerCLI.exe \"MultiFloFX\" \"USB MultiFloFX sn:19041612\"\n" +
                "\tLHC_CallerCLI.exe \"MultiFloFX\" \"USB MultiFloFX sn:19041612\" \"c:\\protocols\\\"\n" +
                "\tLHC_CallerCLI.exe \"405 TS/LS\" \"USB 405 TS/LS sn:191107F\"\n" +
                "\n"
                "This starts a REPL where you can issue these commands:\n"
                "\n" +
                "\tTestCommunications\n" +
                "\tRunProtocol <protocol-path>\n" +
                "\tValidateProtocol <protocol-path>\n" +
                "\tRunLastValidatedProtocol <protocol-path>\n" +
                "\n" +
                "Please read the source code for more details."
            );
        }
    }
}
