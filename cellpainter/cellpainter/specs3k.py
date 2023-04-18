import textwrap

rename_table = str('''
    specs3k P101334 U2OS_P02_L1
    specs3k P101336 U2OS_P03_L1
    specs3k P101338 U2OS_P04_L1
    specs3k P101340 U2OS_P05_L1
    specs3k P101342 U2OS_P06_L1
    specs3k P101344 U2OS_P07_L1
    specs3k P101346 U2OS_P08_L1
    specs3k P101348 U2OS_P09_L1
    specs3k P101350 U2OS_P10_L1
    specs3k P101352 U2OS_P01_L1
    specs3k P101354 U2OS_P11_L1
    specs3k P101356 U2OS_P12_L1
    specs3k P101358 U2OS_P13_L1
    specs3k P101384 U2OS_DMSO_L1
    specs3k P101360 U2OS_P14_L1
    specs3k P101362 U2OS_P15_L1
    specs3k P101364 U2OS_P16_L1
    specs3k P101366 U2OS_P17_L1
    specs3k P101368 U2OS_P18_L1
    specs3k P101370 U2OS_P19_L1
    specs3k P101372 U2OS_P20_L1
    specs3k P101374 U2OS_P21_L1
    specs3k P101376 U2OS_P22_L1
    specs3k P101378 U2OS_P23_L1
    specs3k P101380 U2OS_P24_L1
    specs3k P101382 U2OS_P25_L1
    specs3k P101385 U2OS_DMSO_L2
    specs3k P101335 U2OS_P02_L2
    specs3k P101337 U2OS_P03_L2
    specs3k P101339 U2OS_P04_L2
    specs3k P101341 U2OS_P05_L2
    specs3k P101343 U2OS_P06_L2
    specs3k P101345 U2OS_P07_L2
    specs3k P101347 U2OS_P08_L2
    specs3k P101349 U2OS_P09_L2
    specs3k P101351 U2OS_P10_L2
    specs3k P101353 U2OS_P01_L2
    specs3k P101355 U2OS_P11_L2
    specs3k P101357 U2OS_P12_L2
    specs3k P101359 U2OS_P13_L2
    specs3k P101386 U2OS_DMSO_L3
    specs3k P101361 U2OS_P14_L2
    specs3k P101363 U2OS_P15_L2
    specs3k P101365 U2OS_P16_L2
    specs3k P101367 U2OS_P17_L2
    specs3k P101369 U2OS_P18_L2
    specs3k P101371 U2OS_P19_L2
    specs3k P101373 U2OS_P20_L2
    specs3k P101375 U2OS_P21_L2
    specs3k P101377 U2OS_P22_L2
    specs3k P101379 U2OS_P23_L2
    specs3k P101381 U2OS_P24_L2
    specs3k P101383 U2OS_P25_L2
    specs3k P101387 U2OS_DMSO_L4
    moa-repro P013725 meta25
    moa-repro P013726 meta26
    test_proj (384)P000002 P1_L1
''')

renames: dict[tuple[str, str], str] = {}
for line in textwrap.dedent(rename_table).splitlines():
    if line:
        project, barcode, metadata = line.split()
        renames[project, barcode] = f'{barcode}_{project}_{metadata}'.removeprefix('(384)').replace('-', '_')

