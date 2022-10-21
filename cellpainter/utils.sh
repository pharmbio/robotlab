#!/usr/bin/env bash

set -ueo pipefail

notes=()
note () { notes+=("$1"); }

ROBOT_IP=${ROBOT_IP:-localhost}
ROBOT_PORT=${ROBOT_PORT:-30001}

timeout=${timeout:-1}

note '
    Show info about how the robot will be communicated with.
'
function show-env {
    printf '%s\n' "ROBOT_IP=${ROBOT_IP}"
    printf '%s\n' "ROBOT_PORT=${ROBOT_PORT}"
    printf '%s\n' "timeout=${timeout}"
}

note '
    Run eval "$(./run.sh setup-env)" to set up the robot ip to the robotlab robotarm.

    Prerequisite: Add the robot 10.10.0.112 to .ssh/config as robotlab-ur
'
function setup-env {
    printf '%s\n' "export ROBOT_IP=robotlab-ur"
    printf '%s\n' "export ROBOT_PORT=30001"
}

note '
    Copy localhost files to robotlab and vice versa

    Add the ubuntu robotlab computer to .ssh/config as robotlab-ubuntu
'
function sync-files {
    set -x
    rsync -rtuv ./* robotlab-ubuntu:robot-remote-control
    rsync -rtuv robotlab-ubuntu:robot-remote-control/logs/ logs/
    rsync -rtuv robotlab-ubuntu:robot-remote-control/cache/ cache/
    rsync -rtuv robotlab-ubuntu:robot-remote-control/movelists/ movelists/
}

note '
    Send to the primary protocol on port 30001.

    This protocol accepts urscript programs and continuously dumps a lot
    of binary data in 10hz.  This function sends a UR script using netcat
    which the robot controller executes.
'
function send {
    set -x
    python -c 'import textwrap, sys; print(textwrap.dedent(sys.argv[1]))' "$1" |
        timeout "$timeout" nc $ROBOT_IP $ROBOT_PORT |
        grep --text --only-matching --ignore-case --perl-regexp \
            '(log|assert|program|\w*exception|\w+_\w+:)[\x20-\x7f]*'
}

note '
    The `textmsg` function writes to the polyscope log but is also written
    to this primary protocol. Should output something like this when run:

    PROGRAM_XXX_STARTEDexample
    log p[0.605825,-0.720087,0.233797,-0.0111368,-0.0111357,1.57073]
    PROGRAM_XXX_STOPPEDexample
'
function send-get-tcp-pose {
    send '
        def example():
            textmsg("log ", get_actual_tcp_pose())
        end
    '
}

note '
    The grep in send is set up so that errors and exceptions can be seen.
    This should output something like:

    syntax_error_on_line:3:end:
    compile_error_name_not_found:get_tcp_pose:
'
function send-example-errors {
    send '
        def unbalanced_parens():
            textmsg("log ", get_actual_tcp_pose()
        end
        def undefined_function():
            textmsg("log ", get_tcp_pose())
        end
    '
}

note '
    Set the speed to a value in the range [0.01, 1.00].
    All URScript speeds are affected by this teach pendant speed slider.
'
function set-speed {
    # The speed setting on the teach pendant can be set on the RTDE interface
    # on port 30003. We can send this via the primary protocol for convenience
    # instead.
    #
    # https://forum.universal-robots.com/t/speed-slider-thru-modbus-and-dashboard/8259/2
    send '
        sec set_speed():
            socket_open("127.0.0.1", 30003)
            socket_send_line("set speed '$1'")
            socket_close()
        end
    '
}

note '
    Move in joint space to the neutral space close to the 21 space on the H hotel
'
function send-goto-h21-movej {
    timeout=10
    send '
        def goto_h21_neu():
            set_tcp(p[0, 0, 0, 0, 0, 0])
            neu_deli_p = p[0.208562, -0.360979, 0.806687, 1.570761, 3.7e-05, -8e-06]
            neu_deli_q = [1.705362, -2.020507, 1.674301, 0.345584, 1.705638, -0.001803]
            movej(get_inverse_kin(neu_deli_p, qnear=neu_deli_q), a=1.4, v=1.05)
        end
    '
}

note '
    Go to the neutral space close to h21 and move with coordinates in mm XYZ and degrees RPY.
'
function send-goto-h21-rpy {
    send '
        def rpy_example():
            set_tcp(p[0, 0, 0, -1.2092, 1.2092, 1.2092])

            global last_xyz = [0, 0, 0]
            global last_rpy = [0, 0, 0]
            global last_lin = False

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
            MoveLin(209.1, -428.0, 818.0, -0.8, -4.0, 90.1)
            MoveLin(209.1, -428.0, 818.0, -0.8, -4.0, 90.1)
            MoveLin(209.1, -428.0, 818.0, 0, 0, 90.0)
            MoveRel(0, 0, 0, 0, 0, 10)
            MoveRel(0, 0, 0, 0, 10, -10)
            MoveRel(0, 0, 0, 0, -10, 10)
            MoveRel(0, 0, 0, 0, 0, -10)
        end
    '
}

note '
    With some socket gymnastics it is possible to make the UR robot make a HTTP request.
'
function cobot-curl {
    addr=${1:-www.example.com}
    port=${2:-80}
    url=${3:-/}
    host="$addr:$port"
    timeout=3
    send '
        def curl():
            ok = socket_open("'$addr'", '$port', "curl")
            if not ok:
                textmsg("log failed to curl")
                halt
            end
            socket_send_string("GET / HTTP/1.1", "curl")
            socket_send_byte(13, "curl")
            socket_send_byte(10, "curl")
            socket_send_string("Host: '"$host"'", "curl")
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
        end
    '
}

note '
    Forward the remote robot to localhost via the jumphost
'
function forward-robot-to-localhost {
    set -x
    trap 'kill $(jobs -p)' EXIT
    eval "$(setup-env)"
    ssh -N -L "30001:localhost:30001" -l root "$ROBOT_IP"
}

note '
    Forward the remote robot to localhost then start gui with entr live reloading
'
function forward-robot-then-entr-gui {
    forward-robot-to-localhost &
    sleep 1
    ls *py | entr -c -r cellpainter-moves "$@" --forward
}

note '
    Start gui for simulator
'
function simulator-entr-gui {
    sleep 1
    ls *py | entr -c -r cellpainter-moves "$@" --simulator
}

note '
    Talk to the LabHand 8-bot gripper on TCP port 54321. Use the rs485 urcap.
'
function labhand-test {
    send '
        def main():
            sock = "1"
            textmsg("log opening")
            socket_open("127.0.0.1", 54321, sock)
            textmsg("log opened")
            socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            socket_send_line("s_p_op 97",  sock) textmsg("log ", socket_read_line(sock))
            socket_send_line("s_force 30",  sock) textmsg("log ", socket_read_line(sock))
            socket_send_line("s_p_al 1",  sock) textmsg("log ", socket_read_line(sock))
            sleep(0.2)
            # socket_send_line("m_p_op",  sock) textmsg("log ", socket_read_line(sock))
            socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("m_close", sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            # socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            socket_close(sock)
        end
    '
}

note '
    Home the LabHand 8-bot gripper on TCP port 54321. Use the rs485 urcap.
'
function labhand-home {
    send '
        def main():
            sock = "1"
            textmsg("log opening")
            socket_open("127.0.0.1", 54321, sock)
            textmsg("log opened")
            socket_send_line("home",    sock) textmsg("log ", socket_read_line(sock))
            socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            socket_send_line("g_pos",   sock) textmsg("log ", socket_read_line(sock))
            socket_close(sock)
        end
    '
}


note '
    8-bot reference run
'
function analog-to-gripper {
    o11='"log (1 1) home / close"'
    o10='"log (1 0) open portrait"'
    o01='"log (0 1) open landscape"'
    o00='"log (0 0) power off"'
    s11='"log (1 1) moving"'
    s10='"log (1 0) reached portrait"'
    s01='"log (0 1) reached landscape"'
    s00='"log (0 0) error or powered off"'
    unk='"log (? ?) unknown status"'
    send "
        def gripper():
            set_tool_communication(False, 9600, 0, 1, 1.0, 0.0)
            set_tool_voltage(24)
            set_tool_digital_out(0, True)
            set_tool_digital_out(1, True)
            set_tool_digital_output_mode(0, 1) ## 1: Sinking NPN
            set_tool_digital_output_mode(1, 1) ## 1: Sinking NPN
            set_tool_output_mode(0) ## 0: digital output mode (1: dual pin)
            def outputting():
                t0 = 0
                t1 = 0
                if get_tool_digital_out(0):
                    t0 = 1
                end
                if get_tool_digital_out(1):
                    t1 = 1
                end

                if t0 == 1 and t1 == 1:
                    textmsg($o11)
                elif t0 == 1 and t1 == 0:
                    textmsg($o10)
                elif t0 == 0 and t1 == 1:
                    textmsg($o01)
                elif t0 == 0 and t1 == 0:
                    textmsg($o00)
                else:
                    textmsg($unk)
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
                    textmsg($s11)
                elif t0 == 1 and t1 == 0:
                    textmsg($s10)
                elif t0 == 0 and t1 == 1:
                    textmsg($s01)
                elif t0 == 0 and t1 == 0:
                    textmsg($s00)
                else:
                    textmsg($unk)
                end
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
                outputting()
                set_tool_digital_out(0, b0)
                set_tool_digital_out(1, b1)
                outputting()
                sleep(0.1)
                outputting()
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
            end
            def power_off():
                set(0, 0)
            end
            def open_landscape():
                set(0, 1)
            end
            def open_portrait():
                set(1, 0)
            end
            def close():
                set(1, 1)
            end
            $*
        end
    "
}

note '
    gripper status
'
function analog-gripper-status {
    to-gripper 'status()'
}

note '
    gripper open wide (landscape)
'
function analog-gripper-open-wide {
    to-gripper 'open_landscape()'
}

note '
    gripper open (portrait)
'
function analog-gripper-open {
    to-gripper 'open_portrait()'
}

note '
    gripper close
'
function analog-gripper-close {
    to-gripper 'close()'
}

note '
    gripper landscape
'
function analog-gripper-power-off {
    to-gripper 'power_off()'
}

note '
    gripper home (reference run)
'
function analog-gripper-home {
    to-gripper 'home()'
}

main () {
    if test "$#" -gt 0 && test "$(type -t -- "$1")" = 'function'; then
        "$@"
    else
        self=$(realpath "$0")
        fns=($(grep -Po '^function\s+\K[\w-]+' "$self"))
        {
            printf "Available functions:"
            printf " %s" "${fns[@]}"
            printf "\n\n"
        } | fmt -w $(tput cols)
        for i in "${!fns[@]}"; do
            printf '%s \n' "${fns[i]} ${notes[i]}"
        done
    fi
}

main "$@"
