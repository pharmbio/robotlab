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
    Tool flange: the end point of the last joint where the tool is attached to
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
Jonne's workflow from
https://docs.google.com/spreadsheets/d/17Tc3-pu8PlIvbBNSVf0f7W_Em4n6ECiMjXvrObrig2Y

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

### Robot positions and kinematics

It is not enough to only store points (position + tool rotation) since there are many
possible joint configurations to the same point. (16 for 6-armed robots?)

    joint space: the rotations of the six robot joints
        denoted in radians starting from the base
    q:   joint coordinate
    qd:  joint velocities
    qdd: joint acceleration

    pose: cartesian position of the robot tool center point
          3 cartesian coordinates in metres
          3 rotation vector in radians
    p:    pose coordinate

    inverse kinematics : p -> [q]   # (multi-)mapping cartesian space to joint space
    forward kinematics : q ->  p    # mapping joint space to cartesian space

    Gimbal lock, singularity:
        when the robot loses a degree of movement freedom
        because the joints are positioned above each other

    RPY: roll pitch yaw, a way of denoting the tool rotation similar to polar coordinates.
        not the UR default way to write rotations.

* https://rock-learning.github.io/pytransform3d/rotations.html
* https://www.mecademic.com/en/how-is-orientation-in-space-represented-with-euler-angles
* https://opensource.docs.anymal.com/doxygen/kindr/master/cheatsheet_latest.pdf
* https://forum.universal-robots.com/t/robot-theory-and-how-to-use-it-in-ur-robots/3863/7
* https://www.universal-robots.com/articles/ur/application-installation/explanation-on-robot-orientation/

## URSim: the Simulator

**virtualbox** Easiest is to run the virtualbox version: As of late May 2021 the most recent virtual box version is at:

https://s3-eu-west-1.amazonaws.com/ur-support-site/112647/URSim_VIRTUAL-5.10.2.106319.rar

Enable port forwarding to at least 30001.

**linux version in docker** The best docker image I found is

https://github.com/ahobsonsayers/DockURSim

It allows you to access the PolyScope GUI forwarded to the browser on localhost:8080.

    docker volume create dockursim
    docker run -d --name=dockursim -e ROBOT_MODEL=UR10 \
        --net host -v dockursim:/ursim --privileged --cpus=1 arranhs/dockursim:latest

**linux native** In late May 2021 the latest linux version is at:

https://s3-eu-west-1.amazonaws.com/ur-support-site/105063/URSim_Linux-5.10.0.106288.tar

**other simulators** Open source simulator alternatives include `gazebo`
and `OpenRave` but I have not had time to try any of them

## Robot communication interfaces

| | |
| --- | --- |
| Overview                   | https://www.universal-robots.com/articles/ur/interface-communication/overview-of-client-interfaces/
| Forum thread               | https://forum.universal-robots.com/t/communication-interfaces/29
| port 29999 Dashboard       | https://www.universal-robots.com/articles/ur/dashboard-server-e-series-port-29999/
| port 30001 10hz  primary   | https://www.universal-robots.com/articles/ur/interface-communication/remote-control-via-tcpip/
| port 30002 10hz  secondary | https://www.universal-robots.com/articles/ur/interface-communication/remote-control-via-tcpip/
| port 30003 500hz real-time | https://www.universal-robots.com/articles/ur/interface-communication/remote-control-via-tcpip/
| port 30004 125hz RTDE      | https://www.universal-robots.com/articles/ur/interface-communication/real-time-data-exchange-rtde-guide/
| RTDE c++/python lib        | https://gitlab.com/sdurobotics/ur_rtde
| port 30020                 | Interpreter mode. This is a more recent way of queuing up URScript snippets inside a running URScript with `interpreter_mode()` on.
| xml-rpc                    | URScript function calls xml remote procedure protocol on a http server. Note: that you can do remote communication on sockets using URScript 30001 as well
| modbus                     | An industry standard for robot communication

Read the `robocom.sh` file for examples how to use `nc` to
explore the protocols, in particular the one on port 30001 (primary).

An alternative to `nc` is `socat`. In python use the `socket` module.

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

### URP programs created on the PolyScope handheld tablet

Artifacts produced when making a script on the poly-scope handheld tablet:

- `.urp`: gzipped xml
- `.txt`: textual representation
- `.script`: URScript (Python-esque)

The `.script` file and definitely the `.txt` file is generated from the XML.

The text file is simply this:

```text
 Program
   Robot Program
     MoveJ
       Waypoint_1
```

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

Here:
* `p` is a pose with X,Y,Z in m (metres), and a rotation vector RX,RY,RZ in radians.
* `q` is the six joint positions in radians from base out to the last wrist joint
* `movej` + `get_inverse_kin`:
  Calculate the inverse kinematic transformation (tool space -> joint space).
  If qnear is defined, the solution closest to qnear is returned.
  Otherwise, the solution closest to the current joint positions is returned.

  I don't know why they went via inverse kinematics instead of just generating
  `movej(Waypoint_1_q)`.
* `a` is acceleration in rad/s^2, `v` is velocity in rad/s.

  The default values for `movej` are `a=1.40` and `v=1.05` so this is the
  defaults plus some rounding errors.


### Gripper communication

We use the URScript code from robotiq to work with the gripper.
We had to make a tweak, there is a 1.5 seconds sleep at start up
setting a variable `MSC` to zero, but this variable is always at
zero anyway so we have removed the sleep and it seems to work
anyway. The tweaked script is embedded in `gripper.py`.

Internally the gripper uses a value 0-255 for how open the gripper
is where 0 is open to the max and 255 is closed. We use this
value directly. It's quite opaque but so was their suggested
remapping the range to 0-100%.

This rest of this section is outdated but kept for now.

The gripper is on port 63352 on the robot controller box. This protocol
is unsupported but the one used by the gripper URScript snipped
created by robotiq. I wrote to Robotiq about this and got this reply:

Here's a list of the socket commands, note that these aren't officially
supported and are subject to change in a future release of the URCap.

SET commands:

    ACT activateRequest
    MOD gripperMode
    GTO goto
    ATR automaticReleaseRoutine
    ARD autoreleaseDirection
    MSC maxPeakSupplyCurrent
    POS positionRequest
    SPE speedRequest
    FOR forceRequest
    SCN_BLOCK scanBlockRequest
    SCN scanRequest
    NID updateGripperSlaveId
    SID socketSlaveId

GET commands:

    ACT activateRequest
    MOD gripperMode
    GTO goto
    STA status
    VST vacuumStatus
    OBJ objectDetected
    FLT fault
    MSC maxPeakSupplyCurrent
    PRE positionRequestEcho
    POS positionRequest
    COU motorCurrent
    SNU serialNumber
    PYE productionYear
    NCY numberOfCycles
    PON numberOfSecondsPumpIsOn
    NPA numberOfPumpActivations
    FWV firmwareVersion
    VER driverVersion
    SPE speedRequest
    FOR forceRequest
    DRI printableState
    SID socketSlaveId

These two are also used in the code but were not included in the email I got:

    DST driver_state
    PCO probleme_connection

This is how it looks if you request all values:

```sh
dan@NUC-robotlab:~/robot-remote-control$ printf 'GET %s\n' MOD GTO STA VST OBJ FLT MSC PRE POS COU SNU PYE NCY PON NPA FWV VER SPE FOR DRI SID | timeout 0.1 nc $ROBOT_IP 63352; echo
MOD 0
GTO 1
STA 3
VST 0
OBJ 3
FLT 00
MSC 0
PRE 077
POS 77
COU 0
SNU C-42182
PYE 2019
NCY 2008
PON 135636
NPA 821
FWV GC3-1.6.9
VER DCU-2.0.0
SPE 0
FOR 0
DRI RUNNING
SID [9]
```

If `FLT` is nonzero there is some kind of fault. There should be a LED blinking on the gripper.

The gripper id is 9, so `SID` should be 9.

The robot needs to be activated before run. The gripper is (re-)activated by setting `SET ACT 1`
and it replies with the three bytes `b"ack"`:


```
dan@NUC-robotlab:~/robot-remote-control$ echo SET ACT 1 | timeout 0.1 nc $ROBOT_IP 63352 | xxd
00000000: 6163 6b                                  ack
```

The gripper activation status is in `STA`:
* `STA == 0x00` - Gripper is in reset ( or automatic release )state. See Fault Status if Gripper is activated.
* `STA == 0x01` - Activation in progress.
* `STA == 0x02` - Not used.
* `STA == 0x03` - Activation is completed.

We should also initialize it with:

* lowest speed (`SET SPE 0`) (TODO: maybe this should be `255`)
* lowest force (`SET FOR 0`) (TODO: maybe this should be `255`)
* zero max current (`SET MSC 0`)
* goto mode (`SET GTO 1`)

The robot is closed with `SET POS 255` and opened to a position good for plates with `SET POS 77`:
This is how it looks when closing then opening, re-formatted for clarity:

```sh
$ for POS in 255 77; do { echo SET POS $POS; while true; do printf 'GET %s\n' PRE POS OBJ; sleep 0.8; done } | timeout 5 nc $ROBOT_IP 63352; done
ack
PRE 077   POS  77   OBJ 3
PRE 255   POS 118   OBJ 0
PRE 255   POS 164   OBJ 0
PRE 255   POS 210   OBJ 0
PRE 255   POS 227   OBJ 3
PRE 255   POS 227   OBJ 3
PRE 255   POS 227   OBJ 3
ack
PRE 255   POS 227   OBJ 3
PRE 077   POS 184   OBJ 0
PRE 077   POS 138   OBJ 0
PRE 077   POS  91   OBJ 0
PRE 077   POS  77   OBJ 3
PRE 077   POS  77   OBJ 3
PRE 077   POS  77   OBJ 3
```

It takes a little bit of time after the `ack` for the requested position
to update and `OBJ` to go from 3 into 0. When the motion is completed it is at 3 again. These are the explanations for `OBJ`:

* `OBJ == 0x00`: Fingers are in motion towards requested position. No object detected.
* `OBJ == 0x01`: Fingers have stopped due to a contact while opening before requested position. Object detected opening.
* `OBJ == 0x02`: Fingers have stopped due to a contact while closing before requested position. Object detected closing.
* `OBJ == 0x03`: Fingers are at requested position. No object detected or object has been loss / dropped.

### Liquid handling robots

Possible ways the dispenser could fail:
* no liquid in bottle (only washer has a sensor for this, dispenser will just not dispense anything if liquids run out)
* plate is not correctly inserted (tilted)
    * get stuck when moving plate
    * liquids are dispensed in wrong row/column
* some tips have changed direction, clogged or having droplets
* bacterial/other types of contamination
* liquid does not run away properly and will overflood (vacuum of tube getting to waste)
* liquids runs back in tubing if standing idle for longer than 20 minutes:
    * for cheap solutions (e.g. PFA, TritonX100 and mitotracker: prime)
    * for expensive solutions (stains coctail: pump back (purge) the liquid and prime again)
* liquids need to be primed. Each cassette has a different dead volume and might need different priming protocol.
* wrong waste bottle is connected --> PFA needs to be disposed in  appropiate container”
* plate dropped down blocking the moving parts
* waste bottle is full (liquids will not run off and overflood)
* liquids (e..g stains) stay too long in tubing
* cassettes remain attached which will damage the plastic of the tubing --> remove cassettes after running experiment
* plate is put wrong way around (unlikely with robot though)

Possible ways the washer could fail:
* no liquid in bottle (washer has a sensor for this and will throw an error)
* plate is not correctly inserted
    * get stuck when moving plate
* Z-offset is set wrong for plate (washed off cells or crashes into plate)
* Wrong bottle is selected and wrong liquid is dispensed
* waste bottle is full
* tips are clogged (commonly happens, need to be cleaned by pinching with a needle each of the pins)
