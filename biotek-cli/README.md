# Biotek washer and dispenser CLI
CLI for BioTek Washer and Dispenser.<br>
The CLI is created from modifying the existing BioTek Visual Studio demo project LHC_Caller 5330203 REV 11 V2.20.4

Test run
```
& "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe" "405 TS/LS" "USB 405 TS/LS sn:191107F" "LHC_TestCommunications"
& "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe" "MultiFloFX" "USB MultiFloFX sn:19041612" "LHC_TestCommunications"

& "C:\Program Files (x86)\BioTek\Liquid Handling Control 2.22\LHC_CallerCLI.exe" "405 TS/LS" "USB 405 TS/LS sn:191107F" "LHC_RunProtocol" "C:\ProgramData\BioTek\Liquid Handling Control 2.22\Protocols\test-protocols\washer_prime_buffers_A_B_C_D_25ml.LHC"

```

