#!/bin/sh

set -ueo pipefail

ROBOT_IP=localhost

send () {
    printf '%s\n' "$1" | nc localhost 30001 |
        grep --text --only-matching --ignore-case --perl-regexp \
            '(log|assert|program|\w*exception|\w+_\w+:|index)[\x20-\x7f]*'
}

# socat -v TCP-LISTEN:4321 STDIO &

dont () { true; }
doit () { "$@"; }

send '
def gbl():
    x = 3
end
'

send 'def curl():
    socket_open("192.168.1.68", 8000, "curl")
    socket_send_string("GET / HTTP/1.1", "curl")
    socket_send_byte(13, "curl")
    socket_send_byte(10, "curl")
    socket_send_string("Host: localhost:8000", "curl")
    socket_send_byte(13, "curl")
    socket_send_byte(10, "curl")
    socket_send_string("Accept: */*", "curl")
    socket_send_byte(13, "curl")
    socket_send_byte(10, "curl")
    socket_send_byte(13, "curl")
    socket_send_byte(10, "curl")
    textmsg("log sent all!")
    i = 100
    while i > 0:
        textmsg("log ", socket_read_line("curl"))
        i = i - 1
    end
    socket_close()
end'

dont send 'def spam():
    i = 0
    while i < 10000:
        i = i + 1
        textmsg("log i=", i)
        sleep(0.1)
    end
end'

send 'def T():
    if True: a = 1 v = 2
    else:    a = 2 v = 2
    end
    textmsg("log a ", a)
end
'

send 'def z():
    set_tcp(p[0, 0, 0, -1.2092, 1.2092, 1.2092])

    global last_xyz = [0, 0, 0]
    global last_rpy = [0, 0, 0]
    global last_lin = False

    def test():
        if False:
            textmsg("log true")
            return None
        end
        textmsg("log false")
    end

    test()

    def MoveLin(x, y, z, r, p, yaw):
        rv = rpy2rotvec([d2r(r), d2r(p), d2r(yaw)])
        movel(p[x/1000, y/1000, z/1000, rv[0], rv[1], rv[2]])
        last_xyz = [x, y, z]
        last_rpy = [r, p, yaw]
        last_lin = True
    end

    def MoveRel(x, y, z, r, p, yaw):
        if not last_lin:
            popup("MoveRel without preceding linear move", error=True)
            halt
        end
        MoveLin(
            last_xyz[0] + x, last_xyz[1] + y, last_xyz[2] + z,
            last_rpy[0] + r, last_rpy[1] + p, last_rpy[2] + yaw
        )
    end

    def MoveJoint(q1, q2, q3, q4, q5, q6):
        q = [d2r(q1), d2r(q2), d2r(q3), d2r(q4), d2r(q5), d2r(q6)]
        movej(q)
        last_xyz = [0, 0, 0]
        last_rpy = [0, 0, 0]
        last_lin = False
    end

    MoveJoint(96, -109, 90, 23, 96, 1)
    MoveLin(209.1, -580.1, 818.0, -0.8, -4.0, 90.1)
    MoveLin(209.1, -580.1, 801.3, -0.8, -4.0, 90.1)
    MoveLin(209.1, -580.1, 801.3, 0, 0, 90.0)
    MoveRel(0, 0, 0, 0, 0, 10)
    MoveRel(0, 0, 0, 0, 10, -10)
    MoveRel(0, 0, 0, 0, -10, 10)
    MoveRel(0, 0, 0, 0, 0, -10)
end
'

dont send '
sec test1():
    textmsg("log lol")
    socket_open("192.168.1.68", 4321, "s1")
    socket_send_line("Hello world 1", "s1")
end
def test2():
    textmsg("log lol2")
    socket_open("192.168.1.68", 4321, "s2")
    socket_send_line("Hello world 2", "s2")
end
'

doit send '
def incu():
    set_tcp(p[0, 0, 0, 0, 0, 0])
    delid_neu_p = p[0.209084, -0.397829, 0.822311, 1.640584, -0.010865, 0.011505]
    delid_neu_q = [1.690578, -1.941649, 1.587662, 0.423754, 1.689734, 0.020869]
    movej(delid_neu_q, a=1.4, v=1.05)
    incu_neu_p = p[0.605826, -0.397832, 0.262734, 1.640572, -0.010862, 0.011566]
    movel(incu_neu_p, a=1.2, v=0.25, r=0.32)
    incu_pick_above_p = p[0.605807, -0.720077, 0.262754, 1.640564, -0.010901, 0.011549]
    movel(incu_pick_above_p, a=1.2, v=0.25)
    incu_pick_p = p[0.605825, -0.720087, 0.233797, 1.640554, -0.010878, 0.011601]
    movel(incu_pick_p, a=1.2, v=0.25)
end
'

send 'def example():
    textmsg("log hello")
    popup("error", "fail", error=True, blocking=True)
    # textmsg("log ", get_actual_tcp_pose())
    halt
    # assert(False) # , "lol assert fail")
    # textmsg("log ", get_actual_tcp_pose())
end'

send '
def unbalanced_parens():
    textmsg("log ", get_actual_tcp_pose()
end
def undefined_function():
    textmsg("log ", get_tcp_pose())
end'



dont send 'set_tcp(p[0, 0, 0, 0, 0, 0])'

send '
def x():
    i = 0
    while True:
        i = i + 1
        if i == 1:
            set_tcp(p[0, 0, 0, 0, 0, 0])
        elif i == 2:
            textmsg("log ---")
            set_tcp(p[0, 0, 0, -1.2092, 1.2092, 1.2092])
        elif i == 3:
            break
            set_tcp(p[0, 0, 0, 0, d2r(-90), 0])
        elif i == 4:
            set_tcp(p[0, 0, 0, 0, d2r(90), 0])
        elif i == 5:
            set_tcp(p[0, 0, 0, 0, 0, d2r(90)])
        elif i == 6:
            set_tcp(p[0, 0, 0, 0, 0, d2r(180)])
        elif i == 7:
            set_tcp(p[0, 0, 0, 1.2092, 1.2092, -1.2092])
        else:
            break
        end

        p = str_sub(to_str(get_tcp_offset()), 1)
        textmsg("log var offset p ", p)
        # p = str_sub(to_str(get_actual_tool_flange_pose()), 1)
        # textmsg("log var flange p ", p)
        # p = str_sub(to_str(get_actual_tcp_pose()), 1)
        # textmsg("log var tcp    p ", p)
        tcp = get_actual_tcp_pose()
        rpy = rotvec2rpy([tcp[3], tcp[4], tcp[5]])
        textmsg("log var tcp  rpy ", to_str([r2d(rpy[0]), r2d(rpy[1]), r2d(rpy[2])]))
    end
end'

exit

send 'def m():
      neu_deli_p = p[0.208562, -0.360979, 0.806687, 1.570761, 3.7e-05, -8e-06]
      neu_deli_q = [1.705362, -2.020507, 1.674301, 0.345584, 1.705638, -0.001803]
      movej(get_inverse_kin(neu_deli_p, qnear=neu_deli_q), a=1.4, v=1.05)
end'

exit


send 'def z():
    def MoveLin(x, y, z, r, p, yaw):
        rv = rpy2rotvec([d2r(r), d2r(p), d2r(yaw)])
        movel(p[x/1000, y/1000, z/1000, rv[0], rv[1], rv[2]])
    end

    # MoveLin(400, -400, 700, 115, 0, 90)
    # MoveLin(400, -400, 700, 115, 0, 90)

    # movel(p[0.4, -0.4, 0.7, 1.2 * 1.57, 0, 0])
    # movel(p[0.4, -0.4, 0.7, 1.0 * 1.57, 0, 0])
    # movel(p[0.4, -0.4, 0.7, 0.8 * 1.57, 0, 0])

    # movel(p[0.4, -0.4, 0.7, 0, 0, 1.2 * 1.57])
    # movel(p[0.4, -0.4, 0.7, 0, 0, 1.0 * 1.57])
    # movel(p[0.4, -0.4, 0.7, 0, 0, 0.8 * 1.57])

    # movel(p[0.4, -0.4, 0.7, 0, d2r(180), 0])
    # movel(p[0.4, -0.4, 0.7, 0, d2r(90), 0])
    # movel(p[0.4, -0.4, 0.7, d2r(90), 0, 0])

    # movel(p[0.3, -0.3, 0.8, 0, d2r(90), 0])
    # movel(p[0.3, -0.3, 0.8, 0, d2r(90), 0])

    # set_tcp(p[0,0,0.1, 0,0, -1.57])

    set_tcp(p[0, 0, 0, 0, 1.57, 0])

    textmsg("log var is_steady ", is_steady())
    textmsg("log var        q ", get_actual_joint_positions())

    i = 0
    while True:
        i = i + 1
        if i == 1:
            set_tcp(p[0, 0, 0, 0, d2r(-90), 0])
        elif i == 2:
            set_tcp(p[0, 0, 0, 0, 0, 0])
        elif i == 3:
            set_tcp(p[0, 0, 0, 0, d2r(90), 0])
        else:
            break
        end

        p = str_sub(to_str(get_tcp_offset()), 1)
        textmsg("log var offset p ", p)
        p = str_sub(to_str(get_actual_tool_flange_pose()), 1)
        textmsg("log var flange p ", p)
        p = str_sub(to_str(get_actual_tcp_pose()), 1)
        textmsg("log var tcp    p ", p)
        tcp = get_actual_tcp_pose()
        rpy = rotvec2rpy([tcp[3], tcp[4], tcp[5]])
        textmsg("log var tcp  rpy ", to_str([r2d(rpy[0]), r2d(rpy[1]), r2d(rpy[2])]))
    end

    MoveLin(300, -300, 600, 0, 0, 90)
    # movel(p[0.3, -0.3, 0.8, 1.56644805234595, 0.13704644658253384, -0.13704644658253382])
    # movel(p[0.3, -0.3, 0.8, 0, 0.17, 0])

    # movel(p[0.4, -0.4, 0.7, d2r(80), d2r(90), 0])
    # movel(p[0.4, -0.4, 0.7, d2r(80), d2r(80), 0])
    # movel(p[0.4, -0.4, 0.7, d2r(90), d2r(80), 0])

    i = 20
    while (i > 0):
        i = i - 1
        sleep(0.1)
        textmsg("log var is_steady ", is_steady())
        if is_steady():
            break
        end
    end
end
sec m():
end'


exit

send 'def m():
    def MoveLin(x, y, z, r, p, yaw):
        rv = rpy2rotvec([d2r(r), d2r(p), d2r(yaw)])
        movel(p[x/1000, y/1000, z/1000, rv[0], rv[1], rv[2]])
    end
    MoveLin(208, -552, 806, 90, 0, 0)
end'

send 'def m():
      neu_deli_p = p[0.208562, -0.360979, 0.806687, 1.570761, 3.7e-05, -8e-06]
      neu_deli_q = [1.705362, -2.020507, 1.674301, 0.345584, 1.705638, -0.001803]
      movej(get_inverse_kin(neu_deli_p, qnear=neu_deli_q), a=1.4, v=1.05)
end'

# in python:

send 'sec x():
    textmsg("log ", rotvec2rpy([1.640584, -0.010865,  0.011505]))
    textmsg("log ", rotvec2rpy([1.570761, 3.7e-05,    -8e-06]))
    textmsg("log ", rotvec2rpy([1.209219, -1.2092,    -1.209286]))
    textmsg("log ", rotvec2rpy([1.208008, -1.21114,   -1.211297]))

    textmsg("log ", rpy2rotvec([1.64061, -0.0141082, -8.89856e-05]))
    textmsg("log ", rpy2rotvec([1.57076, 2.86484e-05,1.84616e-05]))
    textmsg("log ", rpy2rotvec([1.5708,  6.43684e-05,-1.57084]))
    textmsg("log ", rpy2rotvec([1.5708,  0.000129466,-1.57352]))
end'
