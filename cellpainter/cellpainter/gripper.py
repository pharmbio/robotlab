gripper_code = str('''
  # Section copied from generated scripts
  set_standard_analog_input_domain(0, 1)
  set_standard_analog_input_domain(1, 1)
  set_tool_analog_input_domain(0, 1)
  set_tool_analog_input_domain(1, 1)
  set_analog_outputdomain(0, 0)
  set_analog_outputdomain(1, 0)
  set_input_actions_to_default()
  set_tool_communication(False, 115200, 0, 1, 1.5, 3.5)
  set_tool_output_mode(0)
  set_tool_digital_output_mode(0, 1)
  set_tool_digital_output_mode(1, 1)
  set_tool_voltage(0)
  set_safety_mode_transition_hardness(1)

  # begin: URCap Installation Node
  #   Source: Robotiq_Grippers, 1.7.1.2, Robotiq Inc.
  #   Type: Gripper
  #aliases for the gripper variable names
  ACT = 1
  GTO = 2
  ATR = 3
  ARD = 4
  FOR = 5
  SPE = 6
  OBJ = 7
  STA = 8
  FLT = 9
  POS = 10
  PRE = 11
  LBP = 12
  LRD = 13
  LBL = 14
  LGN = 15
  MSC = 16
  MOD = 17

  gripper_1_connected = False
  gripper_2_connected = False
  gripper_3_connected = False
  gripper_4_connected = False

  gripper_1_socket_open = False
  gripper_2_socket_open = False
  gripper_3_socket_open = False
  gripper_4_socket_open = False

  gripper_socket_acquire_option = False
  gripper_1_socket_acquired = False
  gripper_2_socket_acquired = False
  gripper_3_socket_acquired = False
  gripper_4_socket_acquired = False

  def rq_init_comm_if_connected(gripper_sid=9, gripper_socket="1"):
      if(not is_gripper_socket_open(gripper_socket)):
        open_gripper_socket(gripper_socket)
      end

      is_gripper_connected = rq_is_gripper_connected(gripper_sid, gripper_socket)
      if(is_gripper_connected):
          rq_set_gripper_connected(gripper_socket)
      end

      return is_gripper_connected
  end

  def open_gripper_socket(gripper_socket):
    is_open = socket_open("127.0.0.1",63352, gripper_socket)
    set_gripper_socket_open(gripper_socket, is_open)
  end

  def is_gripper_socket_open(gripper_socket):
    if(gripper_socket == "1"):
      return gripper_1_socket_open
    elif(gripper_socket == "2"):
      return gripper_2_socket_open
    elif(gripper_socket == "3"):
      return gripper_3_socket_open
    elif(gripper_socket == "4"):
      return gripper_4_socket_open
    else:
      return False
    end
  end

  def set_gripper_socket_open(gripper_socket, is_open):
    if(gripper_socket == "1"):
      gripper_1_socket_open = is_open
    elif(gripper_socket == "2"):
      gripper_2_socket_open = is_open
    elif(gripper_socket == "3"):
      gripper_3_socket_open = is_open
    elif(gripper_socket == "4"):
      gripper_4_socket_open = is_open
    else:
    end
  end

  def rq_is_gripper_connected(gripper_sid=9, gripper_socket="1"):
      socket_set_var("SID", gripper_sid,  gripper_socket)
      ack = socket_read_byte_list(3, gripper_socket, 0.1)
      return is_ack(ack)
  end

  def rq_set_gripper_connected(gripper_id="1"):
      if(gripper_id == "1"):
          gripper_1_connected = True
      end

      if (gripper_id == "2"):
          gripper_2_connected = True
      end

      if (gripper_id == "3"):
          gripper_3_connected = True
      end

      if (gripper_id == "4"):
          gripper_4_connected = True
      end
  end

  def rq_wait_for_gripper_connected():
      gripper_socket = "gripper_conn_socket"
      socket_open("127.0.0.1",63352, gripper_socket)

      retryCtr = 1
      sid_list = rq_get_sid(gripper_socket)
      gripper_is_connected = rq_is_any_gripper_connected(sid_list)

      while(not gripper_is_connected and retryCtr < 2000):
          retryCtr = retryCtr + 1
          sid_list = rq_get_sid(gripper_socket)
          gripper_is_connected = rq_is_any_gripper_connected(sid_list)
      end

      socket_close(gripper_socket)
  end

  def rq_is_any_gripper_connected(sid_list):
      is_gripper_1_connected = rq_is_gripper1_in_sid_list(sid_list)
      is_gripper_2_connected = rq_is_gripper2_in_sid_list(sid_list)
      is_gripper_3_connected = rq_is_gripper3_in_sid_list(sid_list)
      is_gripper_4_connected = rq_is_gripper4_in_sid_list(sid_list)

      if(is_gripper_1_connected or is_gripper_2_connected or is_gripper_3_connected or is_gripper_4_connected):
          return True
      else:
          return False
      end
  end

  def rq_is_gripper_in_sid_list(gripper_sid, sid_list):
      sid_list_length = sid_list[0]
      sid_list_empty_length = 2

      if (sid_list_length <= sid_list_empty_length):
          return False
      end

      sid1 = sid_list[2]
      sid2 = sid_list[5]
      sid3 = sid_list[8]
      sid4 = sid_list[11]

      if(sid1 == gripper_sid or sid2 == gripper_sid or sid3 == gripper_sid or sid4 == gripper_sid):
          return True
      else:
          return False
      end
  end

  def rq_is_gripper1_in_sid_list(sid_list):
      gripper_1_sid_ascii = 57
      return rq_is_gripper_in_sid_list(gripper_1_sid_ascii, sid_list)
  end

  def rq_is_gripper2_in_sid_list(sid_list):
      gripper_2_sid_ascii = 50
      return rq_is_gripper_in_sid_list(gripper_2_sid_ascii, sid_list)
  end

  def rq_is_gripper3_in_sid_list(sid_list):
      gripper_3_sid_ascii = 51
      return rq_is_gripper_in_sid_list(gripper_3_sid_ascii, sid_list)
  end

  def rq_is_gripper4_in_sid_list(sid_list):
      gripper_4_sid_ascii = 52
      return rq_is_gripper_in_sid_list(gripper_4_sid_ascii, sid_list)
  end

  def rq_set_sid(gripper_sid=9, gripper_socket="1"):
      socket_set_var("SID", gripper_sid,  gripper_socket)
      sync()
      ack = socket_read_byte_list(3, gripper_socket)
      return is_ack(ack)
  end

  def rq_get_sid(gripper_socket="1"):
      socket_send_string("GET SID", gripper_socket)
      sync()
      sid_list = socket_read_byte_list(17, gripper_socket)
      sync()
      return sid_list
  end

  def rq_activate(gripper_socket="1"):
      rq_gripper_act = 0

      if (not rq_is_gripper_activated(gripper_socket)):
         rq_reset(gripper_socket)

         while(socket_get_var("ACT",gripper_socket) == 1):
            sleep(0.1)
            rq_reset(gripper_socket)
         end

         rq_set_var(ACT,1, gripper_socket)
      end
  end

  def rq_activate_and_wait(gripper_socket="1"):
      rq_activate(gripper_socket)
      sleep(1.0)

      while(not rq_is_gripper_activated(gripper_socket)):
          # wait for activation completed
      end
      sleep(0.5)
  end

  def rq_activate_all_grippers(reset=False):
      if(gripper_1_connected):
          rq_reset_and_activate("1", reset)
      end

      if(gripper_2_connected):
          rq_reset_and_activate("2", reset)
      end

      if(gripper_3_connected):
          rq_reset_and_activate("3", reset)
      end

      if(gripper_4_connected):
          rq_reset_and_activate("4", reset)
      end

      sleep(0.2)
  end

  def rq_reset_and_activate(gripper_socket="1", reset=False):
      if(reset):
          rq_reset(gripper_socket)
          sleep(0.5)
          rq_activate_and_wait(gripper_socket)
      elif(not rq_is_gripper_activated(gripper_socket)):
          rq_activate_and_wait(gripper_socket)
      end
  end

  def rq_scan_block():
      gripper_socket = "scn_block_socket"
      socket_open("127.0.0.1", 63352, gripper_socket)
      socket_set_var("SCN_BLOCK", 1, gripper_socket)
      sync()
      ack_test = socket_read_byte_list(3, gripper_socket)

      retry_counter = 0

      while(not is_ack(ack_test) and retry_counter < 5):
          socket_set_var("SCN_BLOCK", 1, gripper_socket)
          sync()
          ack_test = socket_read_byte_list(3, gripper_socket)
          retry_counter = retry_counter + 1
      end

      socket_close("scn_block_socket")
  end

  def rq_reset(gripper_socket="1"):
      rq_gripper_act = 0
      rq_obj_detect = 0
      rq_mov_complete = 0

      rq_set_var(ACT,0, gripper_socket)
      rq_set_var(ATR,0, gripper_socket)

      sleep(0.2)
  end

  def rq_auto_release_open_and_wait(gripper_socket="1"):
      rq_set_var(ARD,0, gripper_socket)
      rq_set_var(ACT,1, gripper_socket)
      rq_set_var(ATR,0, gripper_socket)
      sleep(0.1)
      rq_set_var(ATR,1, gripper_socket)

      rq_wait_autorelease_completed(gripper_socket)
  end

  def rq_auto_release_close_and_wait(gripper_socket="1"):
      rq_set_var(ARD,1, gripper_socket)
      rq_set_var(ACT,1, gripper_socket)
      rq_set_var(ATR,0, gripper_socket)
      sleep(0.1)
      rq_set_var(ATR,1, gripper_socket)

      rq_wait_autorelease_completed(gripper_socket)
  end

  def rq_wait_autorelease_completed(gripper_socket="1"):
      retryCounter = 1
      gFLT = rq_get_var(FLT, 2, gripper_socket)

      while(not is_FLT_autorelease_in_progress(gFLT) and retryCounter <= 20):
          retryCounter = retryCounter + 1
          gFLT = rq_get_var(FLT, 2, gripper_socket)
          sleep(0.1)
      end

      retryCounter = 1
      gFLT = rq_get_var(FLT, 2, gripper_socket)

      while(not is_FLT_autorelease_completed(gFLT) and retryCounter <= 100):
          retryCounter = retryCounter + 1
          gFLT = rq_get_var(FLT, 2, gripper_socket)
          sleep(0.1)
      end
  end

  def rq_set_force(force, gripper_socket="1"):
      force = floor(scale(force, [0, 255], [0.0, 127.5]))
      rq_set_var(FOR, force, gripper_socket)
  end

  def rq_set_speed(speed, gripper_socket="1"):
      speed = floor(scale(speed, [0, 255], [0.0, 63.7]))
      rq_set_var(SPE, speed, gripper_socket)
  end

  def rq_open(gripper_socket="1"):
      rq_move(0, gripper_socket)
  end

  def rq_close(gripper_socket="1"):
      rq_move(255, gripper_socket)
  end

  def rq_open_and_wait(gripper_socket="1"):
      rq_move_and_wait(0, gripper_socket)
  end

  def rq_close_and_wait(gripper_socket="1"):
      rq_move_and_wait(255, gripper_socket)
  end

  def rq_move(pos, gripper_socket="1"):
      rq_mov_complete = 0
      rq_obj_detect = 0

      rq_set_pos(pos, gripper_socket)
      rq_go_to(gripper_socket)
  end

  def rq_move_and_wait(pos, gripper_socket="1"):
      rq_move(pos, gripper_socket)

      while (not rq_is_motion_complete(gripper_socket)):
          # wait for motion completed
          sleep(0.01)
          sync()
      end

      # following code used for compatibility with previous versions
      rq_is_object_detected(gripper_socket)

      if (rq_obj_detect != 1):
          rq_mov_complete = 1
      end
  end

  def rq_wait_for_pos_request(pos, gripper_socket="1"):
      gPRE = rq_get_var(PRE, 3, gripper_socket)
      pre = (gPRE[1] - 48)*100 + (gPRE[2] -48)*10 + gPRE[3] - 48

      while (pre != pos):
          rq_set_var(POS, pos, gripper_socket)
          gPRE = rq_get_var(PRE, 3, gripper_socket)
          pre = (gPRE[1] - 48)*100 + (gPRE[2] -48)*10 + gPRE[3] - 48
          sync()
          # The following patch is for Robotiq's Camera issue when communication is lost, but not the activation
          # the communication driver reset the GTO bit
          rq_go_to(gripper_socket)
      end
  end

  def rq_wait_for_pos(pos, gripper_socket="1"):
      rq_wait_for_pos_request(pos, gripper_socket)

      # Wait for the gripper motion to complete
      while (not rq_is_motion_complete(gripper_socket)):
          # wait for motion completed
          sleep(0.01)
          sync()
          rq_go_to(gripper_socket)
      end

      # following code used for compatibility with previous versions
      rq_is_object_detected(gripper_socket)

      if (rq_obj_detect != 1):
          rq_mov_complete = 1
      end
  end

  def rq_wait(gripper_socket="1"):
      # Wait for the gripper motion to complete
      while (not rq_is_motion_complete(gripper_socket)):
          # wait for motion completed
          sleep(0.01)
          sync()
      end

      # following code used for compatibility with previous versions
      rq_is_object_detected(gripper_socket)

      if (rq_obj_detect != 1):
          rq_mov_complete = 1
      end
  end

  def rq_wait_for_object_detected(gripper_socket="1"):
      # Wait the object detection
      while (not rq_is_object_detected(gripper_socket)):
          # wait for motion completed
          sleep(0.01)
          sync()
      end
  end

  # set the position
  def rq_set_pos(pos, gripper_socket="1"):
      pos = floor(scale(pos, [0, 255], [0.0, 255.0]))
      rq_set_var(POS, pos, gripper_socket)
      rq_wait_for_pos_request(pos, gripper_socket)
  end

  # set the position, speed and force
  def rq_set_pos_spd_for(pos, speed, force, gripper_socket="1"):
      rq_acquire_gripper_socket(gripper_socket)
      rq_send_pos_spd_for(pos, speed, force, gripper_socket)
      ack = socket_read_byte_list(3, gripper_socket)
      rq_release_gripper_socket(gripper_socket)

      sync()

      while(is_not_ack(ack)):
          rq_acquire_gripper_socket(gripper_socket)
          rq_send_pos_spd_for(pos, speed, force, gripper_socket)
          ack = socket_read_byte_list(3, gripper_socket)
          rq_release_gripper_socket(gripper_socket)

          sync()
      end

      rq_wait_for_pos_request(pos, gripper_socket)
  end

  def rq_set_gripper_max_current_mA(current_mA, gripper_socket="1"):
      current = floor(current_mA / 10)
      rq_set_var(MSC, current, gripper_socket)
      textmsg("gripper.py skipping sleep 1.5")
      # sleep(1.5)
  end

  def rq_set_gripper_mode(mode, gripper_socket="1"):
      rq_set_var(MOD, mode, gripper_socket)
  end

  def rq_set_gripper_max_cur(current_mA, gripper_socket="1"):
      rq_set_gripper_max_current_mA(current_mA, gripper_socket)
  end

  def rq_get_gripper_max_current_mA(gripper_socket="1"):
      socket_send_string("GET MSC",gripper_socket)
      sync()
      var_value = socket_read_byte_list(3, gripper_socket)

      current = rq_list_of_bytes_to_value(var_value)

      if(current == -1):
          current_mA = current
      else:
          current_mA = current * 10
      end

      return current_mA
  end

  def rq_get_gripper_max_cur(gripper_socket="1"):
      return rq_get_gripper_max_current_mA(gripper_socket)
  end

  def rq_list_of_bytes_to_value(list_of_bytes):
      value = -1

      # response list length
      if (list_of_bytes[0] == 1):
          value = list_of_bytes[1] - 48
      elif (list_of_bytes[0] == 2):
          value = (list_of_bytes[1] - 48) * 10 + (list_of_bytes[2] - 48)
      elif (list_of_bytes[0] == 3):
          value = (list_of_bytes[1] - 48) * 100 + (list_of_bytes[2] - 48) * 10 + (list_of_bytes[3] - 48)
      end

      return value
  end

  # send the position, speed and force
  def rq_send_pos_spd_for(pos, speed, force, gripper_socket="1"):
      pos = floor(scale(pos, [0, 255], [0.0, 255.0]))
      speed = floor(scale(speed, [0, 255], [0.0, 63.7]))
      force = floor(scale(force, [0, 255], [0.0, 127.5]))

      socket_send_string("SET POS", gripper_socket)
      socket_send_byte(32, gripper_socket)
      socket_send_string(pos, gripper_socket)
      socket_send_byte(32, gripper_socket)
      socket_send_string("SPE", gripper_socket)
      socket_send_byte(32, gripper_socket)
      socket_send_string(speed, gripper_socket)
      socket_send_byte(32, gripper_socket)
      socket_send_string("FOR", gripper_socket)
      socket_send_byte(32, gripper_socket)
      socket_send_string(force, gripper_socket)
      socket_send_byte(10, gripper_socket)

      sync()
  end

  def rq_is_motion_complete(gripper_socket="1"):
      rq_mov_complete = 0

      gOBJ = rq_get_var(OBJ, 1, gripper_socket)
      sleep(0.01)

      if (is_OBJ_gripper_at_position(gOBJ)):
          rq_mov_complete = 1
          return True
      end

      if (is_OBJ_object_detected(gOBJ)):
          rq_mov_complete = 1
          return True
      end

      return False

  end

  def rq_is_gripper_activated(gripper_socket="1"):
      gSTA = rq_get_var(STA, 1, gripper_socket)

      if(is_STA_gripper_activated(gSTA)):
          rq_gripper_act = 1
          return True
      else:
          rq_gripper_act = 0
          return False
      end
  end

  def rq_is_object_detected(gripper_socket="1"):
      gOBJ = rq_get_var(OBJ, 1, gripper_socket)

      if(is_OBJ_object_detected(gOBJ)):
          rq_obj_detect = 1
          return True
      else:
          rq_obj_detect = 0
          return False
      end
  end

  def rq_current_pos(gripper_socket="1"):
      rq_acquire_gripper_socket(gripper_socket)
      rq_pos = socket_get_var("POS",gripper_socket)
      rq_release_gripper_socket(gripper_socket)
      sync()
      return rq_pos
  end

  def rq_motor_current(gripper_socket="1"):
      rq_acquire_gripper_socket(gripper_socket)
      rq_current = socket_get_var("COU",gripper_socket)
      rq_release_gripper_socket(gripper_socket)
      sync()
      return rq_current * 10
  end

  def rq_print_connected_grippers():
      if(gripper_1_connected):
          textmsg("Gripper 1 : ", "connected and socket open.")
      end

      if (gripper_2_connected):
          textmsg("Gripper 2 : ", "connected and socket open.")
      end

      if (gripper_3_connected):
          textmsg("Gripper 3 : ", "connected and socket open.")
      end

      if (gripper_4_connected):
          textmsg("Gripper 4 : ", "connected and socket open.")
      end
  end

  def rq_print_gripper_fault_code(gripper_socket="1"):
      gFLT = rq_get_var(FLT, 2, gripper_socket)

      if(is_FLT_no_fault(gFLT)):
          textmsg("Gripper Fault : ", "No Fault (0x00)")
      elif (is_FLT_action_delayed(gFLT)):
          textmsg("Gripper Fault : ", "Priority Fault: Action delayed, initialization must be completed prior to action (0x05)")
      elif (is_FLT_not_activated(gFLT)):
          textmsg("Gripper Fault : ", "Priority Fault: The activation must be set prior to action (0x07)")
      elif (is_FLT_autorelease_in_progress(gFLT)):
          textmsg("Gripper Fault : ", "Minor Fault: Automatic release in progress (0x0B)")
      elif (is_FLT_overcurrent(gFLT)):
          textmsg("Gripper Fault : ", "Minor Fault: Overcurrent protection triggered (0x0E)")
      elif (is_FLT_autorelease_completed(gFLT)):
          textmsg("Gripper Fault : ", "Major Fault: Automatic release completed (0x0F)")
      else:
          textmsg("Gripper Fault : ", "Unknown Fault")
      end
  end

  def rq_print_gripper_num_cycles(gripper_socket="1"):
      socket_send_string("GET NCY",gripper_socket)
      sync()
      string_from_server = socket_read_string(gripper_socket)
      sync()

      if(string_from_server == "0"):
          textmsg("Gripper Cycle Number : ", "Number of cycles is unreachable.")
      else:
          textmsg("Gripper Cycle Number : ", string_from_server)
      end
  end

  def rq_print_gripper_driver_state(gripper_socket="1"):
      socket_send_string("GET DST",gripper_socket)
      sync()
      string_from_server = socket_read_string(gripper_socket)
      sync()

      if(string_from_server == "0"):
          textmsg("Gripper Driver State : ", "RQ_STATE_INIT")
      elif(string_from_server == "1"):
          textmsg("Gripper Driver State : ", "RQ_STATE_LISTEN")
      elif(string_from_server == "2"):
          textmsg("Gripper Driver State : ", "RQ_STATE_READ_INFO")
      elif(string_from_server == "3"):
          textmsg("Gripper Driver State : ", "RQ_STATE_ACTIVATION")
      else:
          textmsg("Gripper Driver State : ", "RQ_STATE_RUN")
      end
  end

  def rq_print_gripper_serial_number(gripper_socket="1"):
      socket_send_string("GET SNU",gripper_socket)
      sync()
      string_from_server = socket_read_string(gripper_socket)
      sync()
      textmsg("Gripper Serial Number : ", string_from_server)
  end

  def rq_print_gripper_firmware_version(gripper_socket="1"):
      socket_send_string("GET FWV",gripper_socket)
      sync()
      string_from_server = socket_read_string(gripper_socket)
      sync()
      textmsg("Gripper Firmware Version : ", string_from_server)
  end

  def rq_print_gripper_driver_version(gripper_socket="1"):
      socket_send_string("GET VER",gripper_socket)
      sync()
      string_from_server = socket_read_string(gripper_socket)
      sync()
      textmsg("Gripper Driver Version : ", string_from_server)
  end

  def rq_print_gripper_probleme_connection(gripper_socket="1"):
      socket_send_string("GET PCO",gripper_socket)
      sync()
      string_from_server = socket_read_string(gripper_socket)
      sync()
      if (string_from_server == "0"):
          textmsg("Gripper Connection State : ", "No connection problem detected")
      else:
          textmsg("Gripper Connection State : ", "Connection problem detected")
      end
  end

  # Returns True if list_of_bytes is [3, 'a', 'c', 'k']
  def is_ack(list_of_bytes):

      # list length is not 3
      if (list_of_bytes[0] != 3):
          return False
      end

      # first byte not is 'a'?
      if (list_of_bytes[1] != 97):
          return False
      end

      # first byte not is 'c'?
      if (list_of_bytes[2] != 99):
          return False
      end

      # first byte not is 'k'?
      if (list_of_bytes[3] != 107):
          return False
      end

      return True
  end

  # Returns True if list_of_bytes is not [3, 'a', 'c', 'k']
  def is_not_ack(list_of_bytes):
      if (is_ack(list_of_bytes)):
          return False
      else:
          return True
      end
  end

  def is_STA_gripper_activated (list_of_bytes):

      # list length is not 1
      if (list_of_bytes[0] != 1):
          return False
      end

      # byte is '3'?
      if (list_of_bytes[1] == 51):
          return True
      end

      return False
  end

  # Returns True if list_of_byte is [1, '1'] or [1, '2']
  # Used to test OBJ = 0x1 or OBJ = 0x2
  def is_OBJ_object_detected (list_of_bytes):

      # list length is not 1
      if (list_of_bytes[0] != 1):
          return False
      end

      # byte is '2'?
      if (list_of_bytes[1] == 50):
          return True
      end

      # byte is '1'?
      if (list_of_bytes[1]  == 49):
          return True
      end

      return False

  end

  # Returns True if list_of_byte is [1, '3']
  # Used to test OBJ = 0x3
  def is_OBJ_gripper_at_position (list_of_bytes):

      # list length is not 1
      if (list_of_bytes[0] != 1):
          return False
      end

      # byte is '3'?
      if (list_of_bytes[1] == 51):
          return True
      end

      return False
  end

  def is_not_OBJ_gripper_at_position (list_of_bytes):

      if (is_OBJ_gripper_at_position(list_of_bytes)):
          return False
      else:
          return True
      end
  end

  #### GTO Section ####
  def rq_stop(gripper_socket="1"):
      rq_set_var(GTO, 0, gripper_socket)
  end

  def rq_set_GTO_and_wait(value, gripper_socket="1"):
      rq_set_var(GTO ,value, gripper_socket)
      while(not is_GTO(value, rq_get_var(GTO, 1, gripper_socket))):
        sync()
      end
  end

  def rq_go_to(gripper_socket="1"):
      rq_set_var(GTO, 1, gripper_socket)
  end


  def is_GTO(goto_value, list_of_bytes):
      zero_ascii = 48
      if (list_of_bytes[0] != 1):
          return False
      end

      if (list_of_bytes[1] == zero_ascii + goto_value):
          return True
      else:
          return False
      end
  end
  #### GTO Section ####

  def is_FLT_no_fault(list_of_bytes):

      # list length is not 2
      if (list_of_bytes[0] != 2):
          return False
      end

      # first byte is '0'?
      if (list_of_bytes[1] != 48):
          return False
      end

      # second byte is '0'?
      if (list_of_bytes[2] != 48):
          return False
      end

      return True

  end

  def is_FLT_action_delayed(list_of_bytes):

      # list length is not 2
      if (list_of_bytes[0] != 2):
          return False
      end

      # first byte is '0'?
      if (list_of_bytes[1] != 48):
          return False
      end

      # second byte is '5'?
      if (list_of_bytes[2] != 53):
          return False
      end

      return True
  end

  def is_FLT_not_activated(list_of_bytes):

      # list length is not 2
      if (list_of_bytes[0] != 2):
          return False
      end

      # first byte is '0'?
      if (list_of_bytes[1] != 48):
          return False
      end

      # second byte is '7'?
      if (list_of_bytes[2] != 55):
          return False
      end

      return True
  end

  def is_FLT_autorelease_in_progress(list_of_bytes):

      # list length is not 2
      if (list_of_bytes[0] != 2):
          return False
      end

      # first byte is '1'?
      if (list_of_bytes[1] != 49):
          return False
      end

      # second byte is '1'?
      if (list_of_bytes[2] != 49):
          return False
      end

      return True

  end

  def is_FLT_overcurrent(list_of_bytes):

      # list length is not 2
      if (list_of_bytes[0] != 2):
          return False
      end

      # first byte is '1'?
      if (list_of_bytes[1] != 49):
          return False
      end

      # second byte is '4'?
      if (list_of_bytes[2] != 52):
          return False
      end

      return True

  end

  def is_FLT_autorelease_completed(list_of_bytes):

      # list length is not 2
      if (list_of_bytes[0] != 2):
          return False
      end

      # first byte is '1'?
      if (list_of_bytes[1] != 49):
          return False
      end

      # second byte is '5'?
      if (list_of_bytes[2] != 53):
          return False
      end

      return True

  end

  def rq_set_var(var_name, var_value, gripper_socket="1"):

      var_name_string = ""

      if (var_name == ACT):
          var_name_string = "ACT"
      elif (var_name == GTO):
          var_name_string = "GTO"
      elif (var_name == ATR):
          var_name_string = "ATR"
      elif (var_name == ARD):
          var_name_string = "ARD"
      elif (var_name == FOR):
          var_name_string = "FOR"
      elif (var_name == SPE):
          var_name_string = "SPE"
      elif (var_name == POS):
          var_name_string = "POS"
      elif (var_name == LBP):
          var_name_string = "LBP"
      elif (var_name == LRD):
          var_name_string = "LRD"
      elif (var_name == LBL):
          var_name_string = "LBL"
      elif (var_name == LGN):
          var_name_string = "LGN"
      elif (var_name == MSC):
          var_name_string = "MSC"
      elif (var_name == MOD):
          var_name_string = "MOD"
      end

      rq_acquire_gripper_socket(gripper_socket)
      socket_set_var(var_name_string, var_value, gripper_socket)
      sync()
      ack = socket_read_byte_list(3, gripper_socket)
      rq_release_gripper_socket(gripper_socket)

      sync()

      while(is_not_ack(ack)):
          rq_acquire_gripper_socket(gripper_socket)
          socket_set_var(var_name_string , var_value, gripper_socket)
          sync()
          ack = socket_read_byte_list(3, gripper_socket)
          rq_release_gripper_socket(gripper_socket)

          sync()
      end
  end


  def rq_get_var(var_name, nbr_bytes, gripper_socket="1"):
      rq_acquire_gripper_socket(gripper_socket)

      if (var_name == FLT):
          socket_send_string("GET FLT", gripper_socket)
      elif (var_name == OBJ):
          socket_send_string("GET OBJ", gripper_socket)
      elif (var_name == STA):
          socket_send_string("GET STA", gripper_socket)
      elif (var_name == PRE):
          socket_send_string("GET PRE", gripper_socket)
      elif (var_name == GTO):
          socket_send_string("GET GTO", gripper_socket)
      else:
      end

      sync()

      var_value = socket_read_byte_list(nbr_bytes, gripper_socket)

      rq_release_gripper_socket(gripper_socket)

      sync()

      return var_value
  end

  def rq_is_object_validated(gripper_selected, gripper_socket="1"):
      if(gripper_selected):
          if(rq_is_object_detected(gripper_socket)):
              return True
          else:
              return False
          end
      else:
          return True
      end
  end

  ############################################
  # normalized functions (maps 0-100 to 0-255)
  ############################################
  def rq_set_force_norm(force_norm, gripper_socket="1"):
      force_gripper = norm_to_gripper(force_norm)
      rq_set_force(force_gripper, gripper_socket)
  end

  def rq_set_speed_norm(speed_norm, gripper_socket="1"):
      speed_gripper = norm_to_gripper(speed_norm)
      rq_set_speed(speed_gripper, gripper_socket)
  end

  def rq_move_norm(pos_norm, gripper_socket="1"):
      pos_gripper = norm_to_gripper(pos_norm)
      rq_move(pos_gripper, gripper_socket)
  end

  def rq_move_and_wait_norm(pos_norm, gripper_socket="1"):
      pos_gripper = norm_to_gripper(pos_norm)
      rq_move_and_wait(pos_gripper, gripper_socket)
  end

  def rq_set_pos_norm(pos_norm, gripper_socket="1"):
      pos_gripper = norm_to_gripper(pos_norm)
      rq_set_pos(pos_gripper, gripper_socket)
  end

  def rq_current_pos_norm(gripper_socket="1"):
      pos_gripper = rq_current_pos(gripper_socket)
      pos_norm = gripper_to_norm(pos_gripper)
      return pos_norm
  end

  def gripper_to_norm(value_gripper):
      value_norm = (value_gripper / 255) * 100
      return floor(value_norm)
  end

  def norm_to_gripper(value_norm):
      value_gripper = (value_norm / 100) * 255
      return ceil(value_gripper)
  end

  def rq_get_position():
      return rq_current_pos_norm()
  end

  def rq_gripper_led_on(gripper_socket="1"):
      rq_set_var(LBP,0, gripper_socket)
  end

  def rq_gripper_led_off(gripper_socket="1"):
      rq_set_var(LBP,1, gripper_socket)
      rq_set_var(LRD,0, gripper_socket)
      rq_set_var(LBL,0, gripper_socket)
      rq_set_var(LGN,0, gripper_socket)
  end

  def rq_gripper_led_force_red(gripper_socket="1"):
      rq_set_var(LBP,1, gripper_socket)
      rq_set_var(LRD,1, gripper_socket)
      rq_set_var(LBL,0, gripper_socket)
      rq_set_var(LGN,0, gripper_socket)
  end

  def rq_gripper_led_force_blue(gripper_socket="1"):
      rq_set_var(LBP,1, gripper_socket)
      rq_set_var(LRD,0, gripper_socket)
      rq_set_var(LBL,1, gripper_socket)
      rq_set_var(LGN,0, gripper_socket)
  end

  def rq_gripper_led_force_green(gripper_socket="1"):
      rq_set_var(LBP,1, gripper_socket)
      rq_set_var(LRD,0, gripper_socket)
      rq_set_var(LBL,0, gripper_socket)
      rq_set_var(LGN,1, gripper_socket)
  end

  def rq_gripper_led_force_purple(gripper_socket="1"):
      rq_set_var(LBP,1, gripper_socket)
      rq_set_var(LRD,1, gripper_socket)
      rq_set_var(LBL,1, gripper_socket)
      rq_set_var(LGN,0, gripper_socket)
  end

  ############################################
  # mm/inches functions
  ############################################
  gripper_closed_norm = [100, 100, 100, 100]
  gripper_open_norm = [0, 0, 0, 0]
  gripper_closed_mm = [0, 0, 0, 0]
  gripper_open_mm = [50, 50, 50, 50]

  def rq_current_pos_mm(gripper_socket=1):
      pos_gripper = rq_current_pos(gripper_socket)
      pos_mm = gripper_to_mm(pos_gripper, gripper_socket)
      return round_value_2_dec(pos_mm)
  end

  def rq_current_pos_inches(gripper_socket=1):
      pos_gripper = rq_current_pos(gripper_socket)
      pos_mm = gripper_to_mm(pos_gripper, gripper_socket)
      pos_in = pos_mm / 25.4
      return round_value_2_dec(pos_in)
  end

  def rq_move_mm(pos_mm, gripper_socket=1):
      pos_gripper = mm_to_gripper(pos_mm, gripper_socket)
      rq_move(pos_gripper, gripper_socket)
  end

  def rq_move_and_wait_mm(pos_mm, gripper_socket=1):
      pos_gripper = mm_to_gripper(pos_mm, gripper_socket)
      rq_move_and_wait(pos_gripper, gripper_socket)
  end

  def rq_move_inches(pos_in, gripper_socket=1):
      pos_mm = pos_in * 25.4
      rq_move_mm(pos_mm, gripper_socket)
  end

  def rq_move_and_wait_inches(pos_in, gripper_socket=1):
      pos_mm = pos_in * 25.4
      rq_move_and_wait_mm(pos_mm, gripper_socket)
  end

  def get_closed_norm(gripper_socket):
      return gripper_closed_norm[gripper_socket - 1]
  end

  def get_open_norm(gripper_socket):
      return gripper_open_norm[gripper_socket - 1]
  end

  def get_closed_mm(gripper_socket):
      return gripper_closed_mm[gripper_socket - 1]
  end

  def get_open_mm(gripper_socket):
      return gripper_open_mm[gripper_socket - 1]
  end

  def set_closed_norm(closed_norm, gripper_socket):
      gripper_closed_norm[gripper_socket - 1] = closed_norm
  end

  def set_open_norm(open_norm, gripper_socket):
      gripper_open_norm[gripper_socket - 1] = open_norm
  end

  def set_closed_mm(closed_mm, gripper_socket):
      gripper_closed_mm[gripper_socket - 1] = closed_mm
  end

  def set_open_mm(open_mm, gripper_socket):
      gripper_open_mm[gripper_socket - 1] = open_mm
  end

  def gripper_to_mm(value_gripper, gripper_socket):
      closed_norm = get_closed_norm(gripper_socket)
      open_norm = get_open_norm(gripper_socket)
      closed_mm = get_closed_mm(gripper_socket)
      open_mm = get_open_mm(gripper_socket)

      value_norm = (value_gripper / 255) * 100

      slope = (closed_mm - open_mm) / (closed_norm - open_norm)
      value_mm = slope * (value_norm - closed_norm) + closed_mm

      if (value_mm > open_mm):
          value_mm_limited = open_mm
      elif (value_mm < closed_mm):
          value_mm_limited = closed_mm
      else:
          value_mm_limited = value_mm
      end

      return value_mm_limited
  end

  def mm_to_gripper(value_mm, gripper_socket):
      closed_norm = get_closed_norm(gripper_socket)
      open_norm = get_open_norm(gripper_socket)
      closed_mm = get_closed_mm(gripper_socket)
      open_mm = get_open_mm(gripper_socket)

      slope = (closed_norm - open_norm) / (closed_mm - open_mm)
      value_norm = (value_mm - closed_mm) * slope + closed_norm

      value_gripper = value_norm * 255 / 100

      if (value_gripper > 255):
          value_gripper_limited = 255
      elif (value_gripper < 0):
          value_gripper_limited = 0
      else:
          value_gripper_limited = round_value(value_gripper)
      end

      return value_gripper_limited
  end

  def round_value(value):
      value_mod = value % 1

      if(value_mod < 0.5):
          return floor(value)
      else:
          return ceil(value)
      end
  end

  def round_value_2_dec(value):
      value_x_100 = value * 100
      value_x_100_rounded = round_value(value_x_100)
      return value_x_100_rounded / 100
  end

  def clear_socket_buffer(gripper_socket="1", read_timeout = 0.1):
    byte_in_buffer = socket_read_byte_list(1, gripper_socket, read_timeout)

    while(byte_in_buffer[0] >= 1):
        byte_in_buffer = socket_read_byte_list(1, gripper_socket, read_timeout)
    end
  end

  def rq_set_gripper_socket_acquire_option(enabled=False):
      gripper_socket_acquire_option = enabled

      if(not enabled):
          gripper_1_socket_acquired = False
          gripper_2_socket_acquired = False
          gripper_3_socket_acquired = False
          gripper_4_socket_acquired = False
      end
  end

  def rq_acquire_gripper_socket(gripper_socket="1"):
      if(gripper_socket_acquire_option):
          rq_wait_gripper_socket_released(gripper_socket)
          enter_critical
              rq_set_gripper_socket_acquired(gripper_socket, True)
          exit_critical

          clear_socket_buffer(gripper_socket, 0.002)

          sync()
      end
  end

  def rq_release_gripper_socket(gripper_socket="1"):
      if(gripper_socket_acquire_option):
          rq_set_gripper_socket_acquired(gripper_socket, False)

          sync()
      end
  end

  def rq_set_gripper_socket_acquired(gripper_socket="1", acquired=False):
      if(gripper_socket == "1"):
          gripper_1_socket_acquired = acquired
      elif(gripper_socket == "2"):
          gripper_2_socket_acquired = acquired
      elif(gripper_socket == "3"):
          gripper_3_socket_acquired = acquired
      elif(gripper_socket == "4"):
          gripper_4_socket_acquired = acquired
      end
  end

  def rq_get_gripper_socket_acquired(gripper_socket="1"):
      if(gripper_socket == "1"):
          return gripper_1_socket_acquired
      elif(gripper_socket == "2"):
          return gripper_2_socket_acquired
      elif(gripper_socket == "3"):
          return gripper_3_socket_acquired
      elif(gripper_socket == "4"):
          return gripper_4_socket_acquired
      end

      sync()
  end

  def rq_wait_gripper_socket_released(gripper_socket="1"):
      while(rq_get_gripper_socket_acquired(gripper_socket)):
          sync()
      end

      sync()
  end

  def rq_gripper_id_to_ascii(gripper_id):
      if(gripper_id == "1"):
          return 57
      elif(gripper_id == "2"):
          return 50
      elif(gripper_id == "3"):
          return 51
      elif(gripper_id == "4"):
          return 52
      end
  end

  def scale(value, rawRange, scaledRange):
      def computeSlope(inputRange, outputRange):
          outputRangeDelta = outputRange[1] - outputRange[0]
          inputRangeDelta = inputRange[1] - inputRange[0]

          if (inputRangeDelta == 0):
              return 0
          else:
              return outputRangeDelta / inputRangeDelta
          end
      end

      def computeIntercept(slope, inputRange, outputRange):
          return outputRange[0] - (slope * inputRange[0])
      end

      def clipScaledValue(outputScaledValue, outputRange):
          if (outputRange[0] < outputRange[1]):
              return clipWhenLowerLimitIsLessThanHigher(outputScaledValue, outputRange)
          else:
              return clipWhenLowerLimitIsGreaterThanHigherLimit(outputScaledValue, outputRange)
          end
      end

      def clipWhenLowerLimitIsGreaterThanHigherLimit(outputScaledValue, outputRange):
          if (outputScaledValue < outputRange[1]):
              return outputRange[1]
          elif (outputScaledValue > outputRange[0]):
              return outputRange[0]
          else:
              return outputScaledValue
          end
      end

      def clipWhenLowerLimitIsLessThanHigher(outputScaledValue, outputRange):
          if (outputScaledValue < outputRange[0]):
              return outputRange[0]
          elif (outputScaledValue > outputRange[1]):
              return outputRange[1]
          else:
              return outputScaledValue
          end
      end

      slope = computeSlope(rawRange, scaledRange)
      intercept = computeIntercept(slope, rawRange, scaledRange)
      scaledValue = slope * value + intercept
      return clipScaledValue(scaledValue, scaledRange)
  end

  def limit(value, range):
      return scale(value, range, range)
  end

  rq_obj_detect = 0
  set_tool_voltage(24)
  set_tool_communication(True, 115200, 0, 1, 1.5, 3.5)
  rq_wait_for_gripper_connected()
  rq_init_comm_if_connected(9, "1")
  rq_init_comm_if_connected(2, "2")
  rq_init_comm_if_connected(3, "3")
  rq_init_comm_if_connected(4, "4")
  rq_print_connected_grippers()
  connectivity_checked = [-1,-1,-1,-1]
  status_checked = [-1,-1,-1,-1]
  current_speed = [-1,-1,-1,-1]
  current_force = [-1,-1,-1,-1]
  set_closed_norm(100.0, 1)
  set_open_norm(0.0, 1)
  set_closed_mm(0.0, 1)
  set_open_mm(50.0, 1)
  set_closed_norm(100.0, 2)
  set_open_norm(0.0, 2)
  set_closed_mm(0.0, 2)
  set_open_mm(50.0, 2)
  set_closed_norm(100.0, 3)
  set_open_norm(0.0, 3)
  set_closed_mm(0.0, 3)
  set_open_mm(50.0, 3)
  set_closed_norm(100.0, 4)
  set_open_norm(0.0, 4)
  set_closed_mm(0.0, 4)
  set_open_mm(50.0, 4)
  rq_set_gripper_max_cur(0, "1")
  # end: URCap Installation Node

  def GripperMove(pos, soft=False):
    if pos > 255:
      pos = 255
    elif pos < 0:
      pos = 0
    end
    while not is_steady():
        sync()
    end
    gripper_1_used = True
    if (connectivity_checked[0] != 1):
      gripper_id_ascii = rq_gripper_id_to_ascii("1")
      gripper_id_list = rq_get_sid("1")
      if not(rq_is_gripper_in_sid_list(gripper_id_ascii, gripper_id_list)):
        popup("Gripper 1 must be connected to run this program.", "No connection", False, True, True)
      end
      connectivity_checked[0] = 1
    end
    if (status_checked[0] != 1):
      if not(rq_is_gripper_activated("1")):
        popup("Gripper 1 is not activated. Go to Installation tab > Gripper to activate it and run the program again.", "Not activated", False, True, True)
      end
      status_checked[0] = 1
    end
    if soft:
        force = 0
    else:
        force = 255
    end
    rq_set_pos_spd_for(pos, 0, force, "1")
    rq_go_to("1")
    rq_wait("1")
    gripper_1_selected = True
    gripper_2_selected = False
    gripper_3_selected = False
    gripper_4_selected = False
    gripper_1_used = False
    gripper_2_used = False
    gripper_3_used = False
    gripper_4_used = False
    pos = rq_current_pos()
    write_output_integer_register(0, pos)  # save gripper position for pharmbio GUI
  end
''')
