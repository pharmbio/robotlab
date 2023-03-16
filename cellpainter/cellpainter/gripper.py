analog_gripper_code = str('''
    StatusMoving = 3
    StatusReachedPortrait = 2
    StatusReachedLandscape = 1
    StatusErrorOrPowerOff = 0

    def log_status(code):
        if code == StatusMoving:
            textmsg("log (1 1) status: moving")
        elif code == StatusReachedPortrait:
            textmsg("log (1 0) status: reached portrait")
        elif code == StatusReachedLandscape:
            textmsg("log (0 1) status: reached landscape")
        elif code == StatusErrorOrPowerOff:
            textmsg("log (0 0) status: error or powered off")
        end
    end

    def log_output():
        t0 = 0
        t1 = 0
        if get_tool_digital_out(0):
            t0 = 1
        end
        if get_tool_digital_out(1):
            t1 = 1
        end
        if t0 == 1 and t1 == 1:
            textmsg("log (1 1) output: home / close")
        elif t0 == 1 and t1 == 0:
            textmsg("log (1 0) output: open portrait")
        elif t0 == 0 and t1 == 1:
            textmsg("log (0 1) output: open landscape")
        elif t0 == 0 and t1 == 0:
            textmsg("log (0 0) output: power off")
        else:
            textmsg("log (? ?) unknown status")
        end
    end
    def status():
        t0 = 0
        t1 = 0
        if get_tool_digital_in(0):
            t0 = 1
        end
        if get_tool_digital_in(1):
            t1 = 1
        end
        if t0 == 1 and t1 == 1:
            code = 3
        elif t0 == 1 and t1 == 0:
            code = 2
        elif t0 == 0 and t1 == 1:
            code = 1
        elif t0 == 0 and t1 == 0:
            code = 0
        end
        log_status(code)
        return code
    end
    def set(t0, t1):
        b0 = False
        b1 = False
        if t0 != 0:
            b0 = True
        end
        if t1 != 0:
            b1 = True
        end
        set_tool_digital_out(0, b0)
        set_tool_digital_out(1, b1)
        status()
        log_output()
        status()
        sleep(0.1)
        status()
        sleep(0.1)
    end
    def home():
        # To start a reference run, set first TO[0] and TO[1] both to
        # logical 0 (0,0) for 2 seconds. Afterwards set TO[0] and TO[1]
        # to (1,1). Keep the status (1,1) as long as the reference
        # run is performed. In case the reference run is interrupted,
        # it has to be started again.
        set(0, 0)
        sleep(2.5)
        set(1, 1)
        sleep(2.0)
        open()
    end
    def power_off():
        set(0, 0)
    end
    def open_landscape():
        set(0, 1)
    end
    def open():
        set(1, 0)
    end
    def close():
        set(1, 1)
    end

    def GripperInit():
        set_tool_communication(False, 9600, 0, 1, 1.0, 0.0)
        set_tool_voltage(24)
        set_tool_digital_out(0, False)
        set_tool_digital_out(1, False)
        set_tool_digital_output_mode(0, 2) ## 1: Sinking NPN, 2: Sourcing PNP
        set_tool_digital_output_mode(1, 2) ## 1: Sinking NPN, 2: Sourcing PNP
        set_tool_output_mode(0) ## 0: digital output mode (1: dual pin)
    end

    def GripperMove(pos, soft=False):
        while not is_steady():
            sync()
        end
        # compability with previous gripper where 255 means close.
        # other numbers we send to portrait
        close = pos == 255
        if close:
            if soft:
                power_off()
                sleep(0.7)
                return 0
            else:
                close()
            end
        else:
            open()
        end

        while 1:
            code = status()
            if code != StatusMoving:
                return 0
            # elif code == StatusErrorOrPowerOff:
            #     textmsg("fatal: code == StatusErrorOrPowerOff")
            # "allowance" is set too small... sigh
            end
            sleep(0.1)
        end
    end
''')

gripper_code = str('''
    global gripper_init = False

    def GripperSend(s, expect=""):
        sock = "1"
        if not gripper_init:
            socket_open("127.0.0.1", 54321, sock)
            gripper_init = True
        end
        retries = 0
        while retries < 10:
            textmsg("log gripper send ", s)
            socket_send_line(s, sock)
            # sleep(0.1)
            while True:
                res = socket_read_line(sock)
                textmsg("log gripper recv ", res)
                if res != "startup":
                    break
                end
            end
            if expect == "":
                return res
            elif res == expect:
                return res
            else:
                textmsg("log retrying ", s)
                retries = retries + 1
            end
        end
        msg = str_cat("Gripper error on ", s) + str_cat(": ", res)
        textmsg("fatal: ", msg)
        popup(msg, "fatal", error=False, blocking=True)
    end

    def GripperPos():
        msg = GripperSend("~g_pos")
        digits = "0"
        i = 0
        while i < str_len(msg):
            c = str_at(msg, i)
            if -1 != str_find("0123456789", c):
                digits = str_cat(digits, c)
            elif str_len(digits) > 1:
                break # outside first contiguous digit sequence
            end
            i = i + 1
        end
        mm_idx = str_find(msg, "mm")
        mm = to_num(digits)
        log_msg = ""
        log_msg = log_msg + str_cat(" msg: '", msg) + "'"
        log_msg = log_msg + str_cat(", mm_idx: ", mm_idx)
        log_msg = log_msg + str_cat(", digits: '", digits) + "'"
        log_msg = log_msg + str_cat(", mm: ", mm)
        textmsg("log gripper", log_msg)
        if -1 != mm_idx and mm > 0:
            write_output_integer_register(0, mm)    # save gripper position for pharmbio GUI
            return mm
        else:
            return -1
        end
    end

    def GripperInit():
        GripperSend("~home", "Parameter successfully set")
        sleep(1.5)
        GripperSend("~s_p_op 97", "Parameter successfully set")
        GripperSend("~s_force 120", "Parameter successfully set")
        sleep(1.5)
        GripperMove(97)
    end

    def GripperMove(pos, soft=False):
        while not is_steady():
            sync()
        end
        # compability with previous gripper where 255 means close.
        # other numbers we send to portrait
        close = pos == 255
        if close:
            if soft:
                GripperSend("~stop", "Parameter successfully set")
            else:
                GripperSend("~m_close", "Parameter successfully set")
            end
        else:
            GripperSend("~m_p_op", "Parameter successfully set")
        end

        # wait for stabilization
        while 1:
            p = GripperPos()
            if p == -1:
                textmsg("log retrying GripperPos, p:", p)
                continue
            end
            if close and p <= 91:
                if 1:
                    sleep(0.15)
                    p = GripperPos()
                    if p > 0 and p <= 80:
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
