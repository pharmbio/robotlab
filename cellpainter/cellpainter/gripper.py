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

        last = GripperPos()

        # wait for stabilization
        while 1:
            # sleep(0.2)
            p = GripperPos()
            if p == -1:
                textmsg("log retrying GripperPos, p: ", p)
                continue
            end
            if p != last:
                textmsg("log not stable yet, keep checking, diff: ", last - p)
                last = p
                continue
            end
            if close and p <= 91:
                if 1:
                    if p > 0 and p <= 81:
                        msg = str_cat("Gripper closed more than expected: ", p) + "mm"
                        textmsg("fatal: ", msg)
                        sleep(10.0)
                    else:
                        textmsg("log gripper close finished at p: ", p)
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
