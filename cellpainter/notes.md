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
    Robotiq: the company that made our previous gripper
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

