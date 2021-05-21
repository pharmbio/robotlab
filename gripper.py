

def code(simulate: bool=False) -> str:
    '''
    Gripper URScript code.

    The public commands are:

        GripperMove,
        GripperClose,
        GripperOpen,
        GripperSocketCleanup.

    They initialize the gripper socket and variables when called the first time.
    Exception: cleanup does not force initialization.
    '''

    private = '''
        def gripper_fail(msg, msg2=""):
            textmsg("log gripper fail ", str_cat(msg, msg2))
            halt
        end

        gripper_initialized = False

        def get_gripper(varname):
            if not gripper_initialized:
                gripper_init()
            end
            socket_send_line(str_cat("GET ", varname), socket_name="gripper") # send "GET PRE\n"
            s = socket_read_string(socket_name="gripper")  # recv "PRE 077\n"
            s = str_sub(s, 4)                              # drop "PRE "
            s = str_sub(s, 0, str_len(s) - 1)              # drop "\n"
            value = to_num(s)
            return value
        end

        def set_gripper(varname, value):
            if not gripper_initialized:
                gripper_init()
            end
            socket_set_gripper(varname, value, socket_name="gripper") # send "SET POS 77\n"
            ack_bytes = socket_read_byte_list(3, socket_name="gripper", timeout=0.1)
            ack = ack_bytes == [3, 97, 99, 107] # 3 bytes received, then ascii for "ack"
            if not ack:
                gripper_fail("gripper request did not ack for var ", varname)
            end
        end

        def gripper_init():
            gripper_initialized = True
            socket_open("127.0.0.1", 63352, socket_name="gripper")
            if get_gripper("STA") != 3:
                gripper_fail("gripper needs to be activated")
            end
            if get_gripper("FLT") != 0:
                gripper_fail("gripper fault")
            end

            set_gripper("GTO", 1)
            set_gripper("SPE", 0)
            set_gripper("FOR", 0)
            set_gripper("MSC", 0)
        end

        def GripperSocketCleanup():
            if gripper_initialized:
                socket_close(socket_name="gripper")
            end
        end
    '''

    public = '''
        def GripperMove(pos):
            set_gripper("POS", pos)
            while (get_gripper("PRE") != pos):
                sleep(0.02)
            end
            while (get_gripper("OBJ") == 0):
                sleep(0.02)
            end
            if get_gripper("OBJ") != 3:
                gripper_fail("gripper move complete but OBJ != 3, OBJ=", get_gripper("OBJ"))
            end
            if get_gripper("FLT") != 0:
                gripper_fail("gripper fault FLT=", get_gripper("FLT"))
            end
        end
    '''

    if simulate:
        public = '''
            def GripperMove(pos):
                textmsg("log gripper simulated, pretending to move to ", pos)
                sleep(0.1)
            end
        '''

    public += '''
        def GripperClose():
            GripperMove(255)
        end

        def GripperOpen():
            GripperMove(77)
        end
    '''

    return private + public

