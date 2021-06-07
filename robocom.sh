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
    Send to the primary protocol on port 30001.

    This protocol accepts urscript programs and continuously dumps a lot
    of binary data in 10hz.  This function sends a UR script using netcat
    which the robot controller executes.
'
function send {
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
function curl-impl {
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
function start-proxies {
    set -x
    trap 'kill $(jobs -p)' EXIT
    ssh -N -L "30001:$ROBOT_IP:30001" -l "$JUMPHOST_USER" "$JUMPHOST" -p "$JUMPHOST_PORT"
}

note '
    Copy localhost files to robotlab and vice versa
'
function sync-files {
    set -x
    rsync -e 'ssh -p 32222' -rtuv ./* robotlab:robot-remote-control
    rsync -e 'ssh -p 32222' -rtuv robotlab:robot-remote-control/logs/ logs/
}

note '
    Copy URP scripts from the robot via $JUMPHOST
'
function copy-urp-scripts {
    set -x
    mkdir -p scripts
    scp -p -o "ProxyJump=$JUMPHOST_USER@$JUMPHOST:$JUMPHOST_PORT" "root@$ROBOT_IP:/data/programs/dan_*" scripts/
}

note '
    Start the gui with entr live-reloading
'
function entr-gui {
    ls *py | entr -r python gui.py "$@"
}

note '
    Start the protocol visualization with entr live-reloading
'
function entr-protocol-vis {
    ls *py | entr -r python protocol_vis.py
}

note '
    Get a plate from the incubator
'
function incu-get {
    python cli.py --test-arm-incu --incu-get "$1"
}

note '
    Put a plate into the incubator
'
function incu-put {
    python cli.py --test-arm-incu --incu-put "$1"
}

note '
    Example of moving four plates from r to incu L
'
function four-plates-from-r-to-incu () {
    # python cli.py --test-arm-incu --robotarm 'r21 get' 'incu put'; incu-put L1
    # python cli.py --test-arm-incu --robotarm 'r19 get' 'incu put'; incu-put L2
    python cli.py --test-arm-incu --robotarm 'r17 get' 'incu put'; incu-put L3
    python cli.py --test-arm-incu --robotarm 'r15 get' 'incu put'; incu-put L4
    python cli.py --test-arm-incu --robotarm 'r13 get' 'incu put'; incu-put L5
    python cli.py --test-arm-incu --robotarm 'r11 get' 'incu put'; incu-put L6
}

note '
    Try to understand what the washer and dispenser are doing
'
function test-wash-disp () {
    while true; do
        curl -s "$1/wash/LHC_TestCommunications" | while read line; do printf 'wash %s\n' "$line"; done
        # curl -s "$1/wash/LHC_GetProtocolStatus"  | while read line; do printf 'wash %s\n' "$line"; done
        curl -s "$1/disp/LHC_TestCommunications" | while read line; do printf 'disp %s\n' "$line"; done
        # curl -s "$1/disp/LHC_GetProtocolStatus"  | while read line; do printf 'disp %s\n' "$line"; done
    done
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
