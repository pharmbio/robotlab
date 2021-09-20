from protocol import ProtocolConfig, Steps

v1 = ProtocolConfig(
    wash = Steps(
        Mito   = 'automation/2_4_6_W-3X_z40.LHC',
        PFA    = 'automation/2_4_6_W-3X_z40.LHC',
        Triton = 'automation/2_4_6_W-3X_FinalAspirate.LHC',
        Stains = 'automation/2_4_6_W-3X_FinalAspirate.LHC',
        Final  = 'automation/8_W-4X_NoFinalAspirate.LHC',
    ),
    prime = Steps(
        Mito   = 'automation/1_D_P1_PRIME.LHC',
        PFA    = 'automation/3_D_SA_PRIME.LHC',
        Triton = 'automation/5_D_SB_PRIME.LHC',
        Stains = 'automation/7_D_P2_PRIME.LHC',
        Final  = '',
    ),
    disp = Steps(
        Mito    = 'automation/1_D_P1_30ul_mito.LHC',
        PFA     = 'automation/3_D_SA_384_50ul_PFA.LHC',
        Triton  = 'automation/5_D_SB_384_50ul_TRITON.LHC',
        Stains  = 'automation/7_D_P2_20ul_STAINS.LHC',
        Final   = '',
    ),
    incu = Steps(30, 20, 20, 20, 0),
    guesstimate_time_wash_3X_minus_incu_pop = 45, # can probably be increased
    guesstimate_time_wash_3X_minus_RT_pop   = 60, # can probably be increased
    guesstimate_time_wash_4X_minus_wash_3X  = 17, # most critical of the guesstimates (!)
)


v2 = ProtocolConfig(
    prep_wash = 'automation_v2/0_W_D_PRIME.LHC',
    prep_disp = None,
    wash = Steps(
        'automation_v2/0_2_W-3X_beforeFixation_leaves20ul.LHC',
        'automation_v2/0_2_W-3X_beforeFixation_leaves20ul.LHC',
        'automation_v2/4_6_W-3X_FinalAspirate.LHC',
        'automation_v2/4_6_W-3X_FinalAspirate.LHC',
        'automation_v2/8_W-4X_NoFinalAspirate.LHC',
    ),
    prime = Steps(
        'automation_v2/1_D_P1_MIX.LHC',
        'automation_v2/3_D_SA_PRIME.LHC',
        'automation_v2/5_D_SB_PRIME.LHC',
        'automation_v2/7_D_P2_PRIME.LHC',
        '',
    ),
    disp = Steps(
       'automation_v2/1_D_P1_80ul_mito_purge.LHC',
       'automation_v2/3_D_SA_384_80ul_PFA.LHC',
       'automation_v2/5_D_SB_384_80ul_TRITON.LHC',
       'automation_v2/7_D_P2_20ul_STAINS.LHC',
       '',
    ),
    incu = Steps(30, 20, 20, 20, 0),
    guesstimate_time_wash_3X_minus_incu_pop = 45, # TODO
    guesstimate_time_wash_3X_minus_RT_pop   = 60, # TODO
    guesstimate_time_wash_4X_minus_wash_3X  = 17, # TODO
)

v2_ms = ProtocolConfig(
    prep_wash='automation_v2_ms/0_W_D_PRIME.LHC',
    prep_disp='automation_v2_ms/0_D_prime_SAB.LHC',
    wash = Steps(
        'automation_v2_ms/1_W-1X_beforeMito_leaves20ul.LHC',
        'automation_v2_ms/3_W-2X_beforeFixation_leaves20ul.LHC',
        'automation_v2_ms/5_W-3X_beforeTriton.LHC',
        'automation_v2_ms/7_W-3X_beforeStains.LHC',
        'automation_v2_ms/9_W-4X_NoFinalAspirate.LHC',
    ),
    prime = Steps(
        'automation_v2_ms/1_D_P1_MIX.LHC',
        'automation_v2_ms/3_D_SA_PRIME.LHC',
        'automation_v2_ms/5_D_SB_PRIME.LHC',
        'automation_v2_ms/7_D_P2_PRIME.LHC',
        '',
    ),
    disp = Steps(
        'automation_v2_ms/2_D_P1_80ul_mito_purge.LHC',
        'automation_v2_ms/4_D_SA_384_80ul_PFA.LHC',
        'automation_v2_ms/6_D_SB_384_80ul_TRITON.LHC',
        'automation_v2_ms/8_D_P2_20ul_STAINS.LHC',
        '',
    ),
    incu = Steps(20, 20, 20, 20, 0),
    guesstimate_time_wash_3X_minus_incu_pop = 110, # TODO
    guesstimate_time_wash_3X_minus_RT_pop   = 60,  # TODO
    guesstimate_time_wash_4X_minus_wash_3X  = 200, # TODO
    delay_before_first_wash         = 0,
    separation_between_first_washes = 0,
    wait_before_incu_get_1st  = Steps(0,60,40,40,40),
    wait_before_incu_get_2nd  = Steps(0,174,0,0,0),
    wait_before_incu_get_rest = Steps(0,174,0,0,0),
)
