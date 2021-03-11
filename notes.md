# Universal Robot notes

Vocabulary outline

    UR: Universal Robot, the robot
    UR: Universal Robots, the Danish company.
    UR10e: the robot we have in the lab.
    Cobot: robot-human collaborative robots. The UR Robots are cobots.
    Teach pendant: the handheld tablet
    PolyScope: the handheld tablet user interface.
    RTDE: Real-time Data Exchange.
    TCP: tool center point, in our case a gripper.
    URCap: a UR capability: a tool attached to the UR (we have a gripper)
    CB: ControlBox, the controller cabinet of the UR robot.
        The controlbox contains the motherboard (Linux PC),
        safety control board (including I/O’s),
        power supplies and
        connection to the teach pendant and robot.
    URScript: a Python-esque script language for programming the robot.
    URP: file extension for scripts made in the PolyScope tablet. This is a gzipped xml.
    Gimbal lock, singularity:
        when the robot loses a degree of movement freedom
        because the joints are positioned above each other

In the lab:

    plate:
        a plate of typically 96 or 384 wells to put cells and chemicals in.
        can have a lid.
        can have a barcode for identification.
        the wells are numbered A1,A2,...,B1,... and its important to not lose how it is oriented.

    hotel: vertical storage rack for plates.
    washer, dispenser:
        the two devices plates are to be processed in.

    incubator:
        plate storage with precise temperature and humidity (looks like a fridge).
        has an entrance slot for the robot to put and get plates.

## Robot communication interfaces

- Overview: https://www.universal-robots.com/articles/ur/interface-communication/overview-of-client-interfaces/
- Forum thread: https://forum.universal-robots.com/t/communication-interfaces/29
    - > It is generally recommended to use RTDE and fieldbus protocols
        (Modbus Client, Ethernet IP or Profinet) rather than the Primary, Secondary,
        Realtime and Dashboard server interfeces.
- port 30001: primary https://www.universal-robots.com/articles/ur/interface-communication/remote-control-via-tcpip/
- port 30002: secondary https://www.universal-robots.com/articles/ur/interface-communication/remote-control-via-tcpip/
- port 30003: real-time https://www.universal-robots.com/articles/ur/interface-communication/remote-control-via-tcpip/
- port 30004: RTDE https://www.universal-robots.com/articles/ur/interface-communication/real-time-data-exchange-rtde-guide/
- port 29999: Dashboard https://www.universal-robots.com/articles/ur/dashboard-server-e-series-port-29999/
- xml-rpc: URScript function calls xml remote procedure protocol on a http server
- modbus: an industry standard for robot communication

### Manual

The manual is surprisingly difficult to find on their web page.

Search for SCRIPT MANUAL - E-SERIES.

https://www.universal-robots.com/download/manuals-e-series/script/script-manual-e-series-sw-56/

### Data mashalling

The different communication formats can dump structs bytes.
The layout of the structs are explained in excel files.
Start with RTDE since it is versioned and only transmits one kind of dump
containing what seems to be all current state.

> URScript does not natively support string handling functions, other
> than comparison, However if the camera is able to transmit a float
> value as ASCII in this format `(1.23, 2.34, 3.45)` it is possible
> directly to receive this, and convert to numerics by the function
> `data = socket_read_ascii_float(n)`

https://forum.universal-robots.com/t/urscript-extensions/1007/2

Getting some data from a socket:

```python
def function1():
   socket_open("127.0.0.1", 33000, "my_socket")
   var1 = socket_read_ascii_float(3, "my_socket")
   textmsg("var1 read as: ", var1)
end
```

https://forum.universal-robots.com/t/debugging-in-urscript/128

### Controlling the gripper

This code for the gripper is generated when you make a script in PolyScope:
```python
   # begin: URCap Program Node
   #   Source: Robotiq_Grippers, 1.7.1.2, Robotiq Inc.
   #   Type: Gripper
   $ 4 "Gripper Open (1)"
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
   rq_set_pos_spd_for(0, 0, 0, "1")
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
   # end: URCap Program Node

   # ... omitted section ...

   $ 6 "Gripper Close (1)"
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
   rq_set_pos_spd_for(255, 0, 0, "1")
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
   # end: URCap Program Node
```

## URP Script programs created on the PolyScope handheld tablet

Artifacts produced when making a script on the poly-scope handheld tablet:

- .urp: gzipped xml
- .txt: textual representation
- .script: URScript (Python-esque)

Hypothesis: the .script file (and definitely the .txt file) is generated from the XML.

In the .urp file we have a waypoint represented like this:
```html
    <Waypoint type="Fixed" name="Waypoint_1" kinematicsFlags="1">
      <motionParameters/>
      <position>
        <JointAngles angles="1.9942498207092285, -1.6684614620604457, 1.9330504576312464, -0.2718423169902344, 1.3209004402160645, 0.0036344528198242188"/>
        <TCPOffset pose="0.0, 0.0, 0.0, 0.0, 0.0, 0.0"/>
        <Kinematics status="LINEARIZED" validChecksum="true">
          <deltaTheta value="-8.844411260213857E-8, -0.032582961261549755, -0.8772929446404238, 0.9098787703504071, 2.101429764675086E-6, -1.9523604853220917E-7"/>
          <a value="1.2280920183406098E-4, -0.6118328650166482, -0.35064142434212725, 6.353071874199852E-5, -8.491717228743712E-5, 0.0"/>
          <d value="0.18107019996630838, -11.986107840354439, 254.02185121292118, -241.86139249326118, 0.11978728860232488, 0.11569307278026907"/>
          <alpha value="1.570573614624119, 0.0016638537326948237, -0.0018631164519257151, 1.5706607381785331, -1.5704473543987978, 0.0"/>
          <jointChecksum value="-1858852621, -1856465696, 659529794, -1323325273, -1859399821, -1861357583"/>
        </Kinematics>
      </position>
      <BaseToFeature pose="0.0, 0.0, 0.0, 0.0, 0.0, 0.0"/>
    </Waypoint>
```

In the .script file the same waypoint and move is represented like this:

```python
  global Waypoint_1_p=p[.433025361705, -.467959205379, .522310714714, 1.500318891221, .521427297251, .530987104689]
  global Waypoint_1_q=[1.9942498207092285, -1.6684614620604457, 1.9330504576312464, -0.2718423169902344, 1.3209004402160645, 0.0036344528198242188]
  $ 1 "Robot Program"
  $ 2 "MoveJ"
  $ 3 "Waypoint_1"
  movej(get_inverse_kin(Waypoint_1_p, qnear=Waypoint_1_q), a=1.3962634015954636, v=1.0471975511965976)
```

There is some coordinate tranformation happening. The coordinate systems seem to be different. I'm not sure which systems are used here.

For reference, the text file is simply this:

```text
 Program
   Robot Program
     MoveJ
       Waypoint_1
```

### movej + `get_inverse_kin`

From the URScript guide:

Calculate the inverse kinematic transformation (tool space -> joint space).
If qnear is defined, the solution closest to qnear is returned.
Otherwise, the solution closest to the current joint positions is returned.

```python
global Waypoint_1_p=p[.434, -.469, .599, 1.500, .521, .530]
global Waypoint_1_q=[1.995, -1.690, 1.815, -0.132, 1.321, 0.003]
movej(get_inverse_kin(Waypoint_1_p, qnear=Waypoint_1_q),
      a=1.396,
      v=1.047)
```

- what is the _actual_ difference between vectors and pose p-vectors?
- what TCP are we using?

However for `get_inverse_kin`:

> If no tcp is provided the currently active tcp of the controller will be used.

    – q = [0.,3.14,1.57,.785,0,0] → joint angles of j0=0 deg, j1=180 deg, j2=90 deg, j3=45 deg, j4=0 deg, j5=0 deg.
    – tcp = p[0,0,0.01,0,0,0] → tcp offset of x=0mm, y=0mm, z=10mm and rotation vector of rx=0 deg., ry=0 deg, rz=0 deg.

## Loose ends

- TODO: Install the simulator `ursim`. (Open source alternatives include `gazebo` and `OpenRave`
- Some UR web pages mention a SDK. I don't know what or where it is

It is not enough to only store points (position + tool rotation) since there are many
possible joint configurations to the same point. (16 for 6-armed robots?)

TODO: How can we get the currently accepted URScript version?

### Gripping the physical plates

    Horizontal or vertical?
    Measurements of the plates
    How "far in" on the the plate do we grip?
    How "far up"?

### Environment

The environment can contain positions. Perhaps we can use these instead of position inside URPs.

