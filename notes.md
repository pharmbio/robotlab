# Universal Robot notes

Vocabulary outline:

    UR: Universal Robot, the robot
    UR: Universal Robots, the Danish company.
    UR10e: the robot we have in the lab.
    Cobot: robot-human collaborative robots. The UR Robots are cobots.
    Freedrive mode: The robot can be positioned by physically moving it
    Teach pendant: the handheld tablet
    PolyScope: the handheld tablet user interface.
    TCP: tool center point, in our case a gripper.
    URCap: a UR capability: a tool attached to the UR (we have a gripper)
    Robotiq: the company that made our gripper
    CB: ControlBox, the controller cabinet of the UR robot.
        The controlbox contains the motherboard (Linux PC),
        safety control board (including I/Os),
        power supplies and
        connection to the teach pendant and robot.
    URScript: a Python-esque script language for programming the robot.
    URP: file extension for scripts made in the PolyScope tablet. This is a gzipped xml.
    RTDE: Real-time Data Exchange, one of the robot protocols.

In the lab:

    plate:
        a plate of typically 384 wells to put cells and chemicals in.
        can have a lid.
        can have a barcode for identification.
        the wells are numbered A1,A2,...,B1,...
        produced by Corning
        technical specifications: PLATE 353962
            https://www.corning.com/catalog/cls/documents/brochures/CLS-DL-CC-016_REV1_DL.pdf ￼￼

        lids from different plates can be put on the same hotel location
        (at different points in time.) no risk for contamination.

    hotel: vertical storage rack for plates.

    washer, dispenser:
        the two devices plates are to be processed in.
        plates must not have a lid.
        plates must have the correct 180° orientation:
            A1 in top-left corner when operating the machine as a human.

        dispenser takes about 30s
        washing takes about 1m30s to 1m40s
        the very last step of washing takes the longest time!

        it's important to move quickly from the washer to the dispenser
        i think this is because then the plates still have some liquid
        on them and don't directly touch the air

    dispenser priming:
        ensures the liquids in the dispenser's tubes are ready and without
        air bubbles if a plate soon will go to the dispenser and it has been
        idle for some minutes run dispenser priming. this takes about 20s

    incubator:
        plate hotel storage with precise temperature (like 37°) and humidity.
        looks like a fridge.
        has an entrance slot for the robot to put and get plates.
        plates must have a lid when they go in and out of the incubator.

         after mitotracker staining has been applied by the dispenser the
         plates go back into the incubator. it's important that the plates
         are in room temperature for as short as possible or the cells die

    shaker:
        another machine for processing plates
        currently not used and not in the lab but occasionally referred to


### Cell painting workflow
From https://docs.google.com/spreadsheets/d/17Tc3-pu8PlIvbBNSVf0f7W_Em4n6ECiMjXvrObrig2Y

<table>
<tr><th>   </th></th><th>  action                                           </th><th>  equipment                         </th><th>  solution                 </th><th>  temp  </th></tr>
<tr><td>1  </td></td><th>  Cell seeding                                     </td><td>  manual/dispenser                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  incubation for 24/48h                            </td><td>  incubator                         </td><td>  -                        </td><td>  37°C  </td></tr>
<tr><td>2  </td></td><th>  Compound treatment                               </td><td>  manual/dispenser/ viaflo/opentrons </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  incubation for 24/48h (can be 10 min difference) </td><td>  incubator                         </td><td>  -                        </td><td>  37°C  </td></tr>
<tr><td>   </td></td><td>  move plate from incubator to washer              </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  Remove (80%) media of all wells                  </td><td>  washer                            </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from washer to dispenser              </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>3  </td></td><th>  Mitotracker staining                             </th><td>  dispenser peripump 1              </td><td>  mitotracker solution     </td><td>  37°C  </td></tr>
<tr><td>   </td></td><td>  move plate from dispenser to incubator           </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>3.1</td></td><td>  Incubation for 30 minutes                        </td><td>  incubator                         </td><td>  -                        </td><td>  37°C  </td></tr>
<tr><td>   </td></td><td>  move plate from incubator to washer              </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>3.2</td></td><td>  Washing                                          </td><td>  washer pump D                     </td><td>  PBS                      </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from washer to dispenser              </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>4  </td></td><th>  Fixation                                         </th><td>  dispenser Syringe A               </td><td>  4% PFA                   </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from dispenser to shaker              </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>4.1</td></td><td>  Incubation for 20 minutes                        </td><td>  shaker                            </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from shaker to washer                 </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>4.2</td></td><td>  Washing                                          </td><td>  washer pump D                     </td><td>  PBS                      </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from washer to dispenser              </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>5  </td></td><th>  Permeabilization                                 </th><td>  dispenser Syringe B               </td><td>  0.1% Triton X-100 in PBS </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from dispenser to shaker              </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>5.1</td></td><td>  Incubation for 20 minutes                        </td><td>  shaker                            </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from shaker to washer                 </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>5.2</td></td><td>  Washing                                          </td><td>  washer pump D                     </td><td>  PBS                      </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from washer to shaker                 </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>6  </td></td><th>  Post-fixation staining                           </th><td>  dispenser peripump 2              </td><td>  staining mixture in PBS  </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from dispenser to shaker              </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>6.1</td></td><td>  Incubation - 20 minutes                          </td><td>  shaker                            </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from shaker to washer                 </td><td>  robot arm/manual                  </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>6.2</td></td><td>  Washing                                          </td><td>  washer pump D                     </td><td>  PBS                      </td><td>  RT    </td></tr>
<tr><td>   </td></td><td>  move plate from washer to IMX                    </td><td>  manual                            </td><td>  -                        </td><td>  RT    </td></tr>
<tr><td>7  </td></td><th>  Imaging                                          </th><td>  microscope                        </td><td>  -                        </td><td>  RT    </td></tr>
</table>


### Lab camera
The surveillance camera in the lab can be found on https://monitor.pharmb.io.

### Gripping the physical plates

**Lidded plates:** When moving lidded plates it is not possible to only grab
the top part (since then you only grab the lid).  Instead we tilt the arm
a bit (a few degrees) and grab for the center section. This is for example
needed by the incubator.

**Horizontal or vertical**: For now we have only needed horizontal
grips. Vertical grips are difficult by the washer and dispenser because the
arm collides with the machine.

It is not enough to only store points (position + tool rotation) since there are many
possible joint configurations to the same point. (16 for 6-armed robots?)
- **inverse kinematics** (multi-)mapping cartesian space to joint space
- **forward kinematics** mapping joint space to cartesian space

### Robot positions and kinematics

    joint space: the rotations of the six robot joints
        denoted in radians starting from the base
    q:   joint coordinate
    qd:  joint velocities
    qdd: joint acceleration

    pose: cartesian position of the robot tool center point
        3 cartesian coordinates in metres
        3 axis-angle in radians
    p:   pose coordinate

    Gimbal lock, singularity:
        when the robot loses a degree of movement freedom
        because the joints are positioned above each other

    RPY: roll pitch yaw, a way of denoting the tool rotation similar to polar coordinates.
        not the UR default way to write rotations.

https://www.universal-robots.com/articles/ur/application-installation/explanation-on-robot-orientation/
https://www.mecademic.com/en/how-is-orientation-in-space-represented-with-euler-angles
https://www.researchgate.net/publication/336061230_An_image_vision_and_automatic_calibration_system_for_universal_robots

## URSim: the Simulator

The best docker image I found is https://github.com/ahobsonsayers/DockURSim
It allows you to access the PolyScope GUI forwarded to the browser on localhost:8080.

    docker volume create dockursim
    docker run -d --name=dockursim -e ROBOT_MODEL=UR10 \
        -p 8080:8080 -p 29999:29999 -p 30001-30004:30001-30004 \
        -v dockursim:/ursim --privileged --cpus=1 arranhs/dockursim:latest

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
- port 30020: Interpreter mode. This is a more recent way of queuing up URScript snippets inside a running URScript with `interpreter_mode()` on.
- xml-rpc: URScript function calls xml remote procedure protocol on a http server
- modbus: an industry standard for robot communication

Using the simulator, this is how some of the protocols look like.
We will use netcat `nc`. Another alternative is `socat`.
In python use the `socket` module.

### port 29999: Dashboard

A few high-level commands can be sent here.

    $ nc localhost 29999
    Connected: Universal Robots Dashboard Server

Now we can type things like `running` and `programState` and it will reply:

    $ nc localhost 29999
    Connected: Universal Robots Dashboard Server
    running
    Program running: false
    programState
    STOPPED <unnamed>

### port 30001: primary

This protocol accepts urscript programs and continuously dumps a lot of binary data in 10hz.

    $ nc localhost 30001 | xxd | head
    00000000: 0000 0037 14ff ffff ffff ffff fffe 0309  ...7............
    00000010: 5552 436f 6e74 726f 6c05 0400 0000 0000  URControl.......
    00000020: 0000 0032 312d 3036 2d32 3031 392c 2031  ...21-06-2019, 1
    00000030: 303a 3033 3a30 3200 0000 1814 ffff ffff  0:03:02.........
    00000040: ffff ffff fe0c 0000 0000 0000 0000 0100  ................
    00000050: 0000 b518 3fc3 3333 3333 3333 4039 0000  ....?.333333@9..
    00000060: 0000 0000 0000 0000 0000 0000 4000 0000  ............@...
    00000070: 0000 0000 3fc9 9999 9999 999a 3fc9 9999  ....?.......?...
    00000080: 9999 999a 3fc9 9999 9999 999a 3fc9 9999  ....?.......?...
    00000090: 9999 999a 3fc9 9999 9999 999a 3fc9 9999  ....?.......?...
    write(stdout): Broken pipe

This example sends a script which the robot controller executes.  The `textmsg` function
writes to the polyscope log but is also written to this primary protocol.

    $ printf '%s\n' 'def silly():' ' textmsg("nonce nonce nonce pharmbio says hello")' end |
        timeout 1 netcat localhost 30001 | xxd | grep -A 2 nonce
    000009f0: 0000 03d0 6e4f 00fd 006e 6f6e 6365 206e  ....nO...nonce n
    00000a00: 6f6e 6365 206e 6f6e 6365 2070 6861 726d  once nonce pharm
    00000a10: 6269 6f20 7361 7973 2068 656c 6c6f 0000  bio says hello..
    00000a20: 0010 19ff ffff ffff ffff ff01 0000 0000  ................

We also get `PROGRAM_XXX_STARTED` messages when program starts and a similar
when it stops:

    $ printf '%s\n' 'def silly():' end |
        timeout 1 netcat localhost 30001 |
        xxd | grep -A 2 -P '[PROGRAM_X_silly]{3}'
    000009d0: 0013 5052 4f47 5241 4d5f 5858 585f 5354  ..PROGRAM_XXX_ST
    000009e0: 4152 5445 4473 696c 6c79 0000 0030 1400  ARTEDsilly...0..
    000009f0: 0000 03df 7e0d 50fd 0700 0000 0000 0000  ....~.P.........
    00000a00: 0013 5052 4f47 5241 4d5f 5858 585f 5354  ..PROGRAM_XXX_ST
    00000a10: 4f50 5045 4473 696c 6c79 0000 0010 19ff  OPPEDsilly......
    00000a20: ffff ffff ffff ff01 0000 0000 0009 0500  ................
    00000a30: 0000 0000 0002 cc10 0000 002f 0000 0000  .........../....

We also get errors when trying to run scripts:

    $ printf '%s\n' 'def silly()' end |
        timeout 1 netcat localhost 30001 |
        xxd | grep -C 1 -P [error_]{3}
    00000450: 0000 0032 14ff ffff ffff ffff fffd 0a00  ...2............
    00000460: 0000 0200 0000 0173 796e 7461 785f 6572  .......syntax_er
    00000470: 726f 725f 6f6e 5f6c 696e 653a 323a 656e  ror_on_line:2:en
    00000480: 643a 0000 056a 1000 0000 2f00 0000 0003  d:...j..../.....
    $ printf '%s\n' 'def silly():' ' txtmsg("")' end |
        timeout 1 netcat localhost 30001 |
        xxd | grep -C 1 -P [error_]{3}
    00000450: 0000 003b 14ff ffff ffff ffff fffd 0a00  ...;............
    00000460: 0000 0200 0000 0263 6f6d 7069 6c65 5f65  .......compile_e
    00000470: 7272 6f72 5f6e 616d 655f 6e6f 745f 666f  rror_name_not_fo
    00000480: 756e 643a 7478 746d 7367 3a00 0005 6a10  und:txtmsg:...j.

The actual layout of the binary data packages is outlined in an excel file.
I spent some time parsing the excel file and then unpacking the structs.
This was brittle and we won't need all that data. If we do we can get
it through easier means. Notably, judicious use of `textmsg` can make the
robot reply any data available inside URScripts. This example obtains
the current joint space coordinates:

    $ printf '%s\n' 'def silly():' ' textmsg("BEGIN ", str_cat(get_actual_joint_positions(), " END"))' end |
        timeout 1 netcat localhost 30001 |
        cat -v | grep -oP 'BEGIN.*?END'
    BEGIN [1.2, -1.125651, -2, 0, -0, 0] END

## Scripting the robot: URScript and .URP files

- URScript: a Python-esque script language for programming the robot.
- URP: file extension for scripts made in the PolyScope tablet. This is a gzipped xml.

### URScript manual

The URScript manual is surprisingly difficult to find on their web page.
The manual is also quite hard to read because it is not well typeset (update:
the newer version is better in this respect) and functions are mostly sorted
by name and not functionality.  Nevertheless, it is an absolute must read.

Search for SCRIPT MANUAL - E-SERIES.

https://www.universal-robots.com/download/manuals-e-series/script/script-manual-e-series-sw-56/
https://www.universal-robots.com/download/manuals-e-series/script/script-manual-e-series-sw-510/

### URScript and the teach pendant speed slider

All URScript speeds are affected by the teach pendant speed slider. Luckily,
it seems like it can be set using code on the RTDE interface:

https://forum.universal-robots.com/t/speed-slider-thru-modbus-and-dashboard/8259/2

You can access the slider through a socket connection to port 30003. Here is an
example of a script function we use to set the speed slider programmatically
within a robot program. You could also send this from an external source,
PLC or PC, if you open a client to the server similar to sending a command
to the dashboard server.

```python
def runSlow(speed):
  socket_open("127.0.0.1",30003)
  socket_send_string("set speed")
  socket_send_string(speed)  # float in range 0.01 to 1.00
  socket_send_byte(10)
  socket_close()
end
``` ￼￼

### URP programs created on the PolyScope handheld tablet

Artifacts produced when making a script on the poly-scope handheld tablet:

- `.urp`: gzipped xml
- `.txt`: textual representation
- `.script`: URScript (Python-esque)

Hypothesis: the `.script` file (and definitely the `.txt` file) is generated from the XML.

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

### URScript: controlling the gripper

Use the generated code when making a script in PolyScope.

This code for the gripper is generated when you make a script in PolyScope. It
looks like this:

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
```

### movej + `get_inverse_kin`

From the URScript guide:

Calculate the inverse kinematic transformation (tool space -> joint space).
If qnear is defined, the solution closest to qnear is returned.
Otherwise, the solution closest to the current joint positions is returned.

```python
global Waypoint_1_p=p[.434, -.469, .599, 1.500, .521, .530]
global Waypoint_1_q=[1.995, -1.690, 1.815, -0.132, 1.321, 0.003]
movej(get_inverse_kin(Waypoint_1_p, qnear=Waypoint_1_q), a=1.396, v=1.047)
```

## Loose ends

- Some UR web pages mention a SDK. I don't know what or where it is. It could be that they meant the URCap SDK.
- Open source simulator alternatives include `gazebo` and `OpenRave`.
- How can we get the currently accepted URScript version? Version incompabilities has not been a problem yet though.
