gripper_code = str('''
  global gripper_init = False

  def GripperSend(s, expect=""):
    sock = "1"
    if not gripper_init:
      socket_open("127.0.0.1", 54321, sock)
      gripper_init = True
    end
    textmsg("log gripper send ", s)
    socket_send_line(s, sock)
    sleep(0.1)
    while True:
      res = socket_read_line(sock)
      textmsg("log gripper recv ", res)
      if res != "startup":
        break
      end
    end
    if expect != "":
      if res != expect:
        msg = str_cat("Gripper error on ", s) + str_cat(": ", res)
        textmsg("fatal: ", msg)
        popup(msg, "fatal", error=False, blocking=True)
      end
    end
    return res
  end

  def GripperPos():
    msg_mm = GripperSend("~g_pos")
    mm_idx = str_find(msg_mm, "mm")
    # textmsg("log mm_idx: ", mm_idx)
    if mm_idx > 0:
      current_mm = to_num(str_sub(msg_mm, 0, mm_idx))
      textmsg("log current_mm: ", current_mm)
      write_output_integer_register(0, current_mm)  # save gripper position for pharmbio GUI
      return current_mm
    else:
      return -1
    end
  end

  def GripperInit():
    GripperSend("~home", "Parameter successfully set")
    sleep(1.5)
    GripperSend("~s_p_op 97", "Parameter successfully set")
    GripperSend("~s_force 30", "Parameter successfully set")
    sleep(0.1)
  end

  def GripperMove(pos, soft=False):
    while not is_steady():
      sync()
    end
    # compability with previous gripper where 255 means close.
    # other numbers we send to portrait
    close = pos == 255
    if close:
      GripperSend("~m_close", "Parameter successfully set")
    else:
      GripperSend("~m_p_op", "Parameter successfully set")
    end

    # wait for stabilization
    while 1:
      p = GripperPos()
      if close and p <= 90:
        if 0:
          sleep(0.15)
          p = GripperPos()
          if p <= 80:
            msg = str_cat("Gripper closed more than expected: ", p) + "mm"
            textmsg("fatal: ", msg)
            popup(msg, "fatal", error=False, blocking=True)
          end
        end
        break
      end
      if not close and p >= 97:
        break
      end
    end
  end

  def GripperMoveTo(pos_mm, soft=False):
    # this makes the gripper start to wobble
    if pos_mm > 140:
      pos_mm = 140
    elif pos_mm < 70:
      pos_mm = 70
    end

    GripperSend(str_cat("~m_pos ", pos_mm), "Parameter successfully set")

    while GripperPos() != pos_mm:
      sync()
    end
  end
''')
