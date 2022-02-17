# Standard operating procedure for robot-cellpainter

For dry runs.

For actual cell painting the protocol is similar but preparation and post-work
for washer, dispenser and incubator are more involved.

## Start gui on robotlab-ubuntu

The robotlab-ubuntu computer is the NUC running ubuntu.

Log in as `pharmbio`, go to the directory for the repo, `~/robot-cellpainter/`.

<details>
<summary>Detailed instructions...</summary>

On the windows computer start PowerShell.

```
ssh pharmbio@10.10.0.55
```

The output should look like:

```
PS C:\Users\pharmbio> ssh pharmbio@10.10.0.55
pharmbio@10.10.0.55's password:
Welcome to Ubuntu 20.04.2 LTS (GNU/Linux 5.4.0-77-generic x86_64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/advantage

232 updates can be installed immediately.
83 of these updates are security updates.
To see these additional updates run: apt list --upgradable

*** System restart required ***
Last login: Wed Feb 16 16:06:11 2022 from 10.10.0.10
Welcome to Ubuntu 20.04.2 LTS (GNU/Linux 5.4.0-77-generic x86_64)

 * Documentation:  https://help.ubuntu.com
 * Management:     https://landscape.canonical.com
 * Support:        https://ubuntu.com/advantage

232 updates can be installed immediately.
83 of these updates are security updates.
To see these additional updates run: apt list --upgradable

*** System restart required ***
Last login: Wed Feb 16 16:06:11 2022 from 10.10.0.10
pharmbio@NUC-robotlab:~$
```

Continue in this shell:

```
cd robot-cellpainter
VIABLE_HOST=10.10.0.55 cellpainter-gui --live
```
</details>

1. Make sure you are running the desired version of the code. Use `git pull`, `git log`, `git status`, `git reset`, etc.

2. Start the gui:

   ```
   VIABLE_HOST=10.10.0.55 cellpainter-gui --live
   ```

3. Use the windows computer and verify that you can go to http://10.10.0.55:5000.

## Incubator preparation

1. Turn on incubator

## Washer preparation

1. Turn on washer

2. Attach water from green tap to pump D

3. Attach the waste bottle

## Dispenser preparation

1. Turn on dispenser

2. Attach the casettes to the peristaltic pumps

3. Run either with air (do nothing more) or with water from green tap

3. If running with water: attach an empty waste bottle or one used only with water and ethanol

## Robot arm preparation

Use the teach pendant.

1. Power on the robotarm

2. Activate the robot arm gripper

3. Clean the robot gripper fingers so that they are free of dust. Use ethanol.

4. Move the robot arm to the neutral position (in front of the B21 hotel rack)

   With the teach pendant, hold down the freedrive button on the back side

5. Put the robot in remote mode

6. Put the teach pendant close to the keyboard so you can reach the emergency button

7. Use the windows computer and go to http://10.10.0.55:5000.

8. Run the test communications protocol, `test-comm` to verify that all machines can be communicated with.

    <details>
    <summary>Alternative: use the command line</summary>

    Use `pharmbio@robotlab-ubuntu` in the directory for the repo, `~/robot-cellpainter/`.

    ```
    cellpainter --test-comm --live
    ```

    </details>

   Common ways this can fail:

   * Robotarm might be in local mode. Change it to remote mode on the teach pendant.

   * Robotarm gripper might not be activated. Activate it using the teach pendant.

   * Incubator communication might not be activated. Run the `incu-reset-and-activate` protocol.

    <details>
    <summary>Alternative: use the command line</summary>
    ```
    curl http://10.10.0.56:5050/incu/reset_and_activate
    ```
    </details>

   * If 10.10.0.56:5050 cannot be reached make sure the
     robotlab-windows computer is running the labrobots server:
     https://github.com/pharmbio/robotlab-labrobots

9. Run the test circuit protocol, `test-circuit`, to see that everything is in the correct place.
   This is optional if you know everything is in order.

   Start with one plate with lid in the incubator transfer door.

   If moves fail: move the instruments to their correct locations. If that is
   not possible update the locations using the `cellpainter-moves` program.

    <details>
    <summary>Alternative: use the command line</summary>

    Use `pharmbio@robotlab-ubuntu` in the directory for the repo, `~/robot-cellpainter/`.

    ```
    cellpainter --test-circuit --live
    ```

    </summary>

## Test plate decontamination

The purpose of this step is to make the test plates safe and clean to be used inside the incubator.
If they have any dirt the incubator quickly gets contaminated. If the clean plate are
touched by hand without gloves they are not considered clean any more and must not enter the incubator.

1. Put test plates in Virkon for a few hours

2. Prepare for --wash-plates-clean:

2.1 Put plates in A1, A3, ...

2.2 Attach washer pump D to water from green tap

2.3 Attach washer pump C to ethanol

2.4 Attach washer waste bottle, preferably an empty one or one just used with water and ethanol

3. Use the gui on the windows computer at http://10.10.0.55:5000, select `wash-plates-clean` and enter the number of plates. Press start!

    <details>
    <summary>Alternative: use the command line</summary>

    Use `pharmbio@robotlab-ubuntu` in the directory for the repo, `~/robot-cellpainter/`.

    ```
    cellpainter --wash-plates-clean --num-plates $NUM_PLATES --live
    ```
    </summary>

4. After wash-plates-clean:

4.1 Prime the washer tubes empty

4.2 Detach the washer waste bottle. If it contains only water and ethanol: empty it in the sink

4.3 Your plates are now safe! Safe plates may enter the incubator. They must not be touched without gloves.

## Loading the incubator

1. Place the plates in A1, A3, A5, ... They will be moved to L1, L2, L3, ... inside the
   incubator. L1 is the first plate to be painted, L2 the second, and so on.

2. Make sure the robot is in neutral position (in front of the B21 hotel rack).

   Use the teach pendant and its freedrive button.

3. Use the windows computer and go to http://10.10.0.55:5000.

4. Use the load incubator protocol, `incu-load`, and enter the number of plates. Press start!

    <details>
    <summary>Alternative: use the command line</summary>

    Use `pharmbio@robotlab-ubuntu` in the directory for the repo, `~/robot-cellpainter/`.

    ```
    cellpainter --load-incu --num-plates $NUM_PLATES --live
    ```

    </summary>

## Painting

1. Clean the robot gripper fingers so that they are free of dust.

2. Make sure the robot is in neutral position (in front of the B21 hotel rack)

   Use the teach pendant and its freedrive button.

3. Use the windows computer and go to http://10.10.0.55:5000.

4. Select the `cell-paint` protocol and enter the desired settings. Press start!

    <details>
    <summary>Alternative: use the command line</summary>

    Use `pharmbio@robotlab-ubuntu` in the directory for the repo, `~/robot-cellpainter/`.

    ```
    cellpainter --cell-paint $BATCH_SIZES [--interleave] [--lockstep] [--two-final-washes] [--incu $INCU_CSV] --live
    ```
    </summary>

## After painting

1. If you want to store the log file (always do this for actual cell painting experiments),
   on the robotlab-ubuntu computer add the log file to git and push it:

   ```
   cd robot-cellpainter
   git add --force logs/2022-12-15_13:52:31-from-gui.jsonl
   git commit -m 'Add logs from estrogen receptor experiment, batch 1 of 4'
   git push
   ```

2. Return the robot to local mode

3. For dry run: Empty the washer tubings by priming them

4. For dry run: Detach the washer waste bottle and dispose it if it is only water

5. For dry run and dispenser was run with water: Empty tubings by priming them and dispose the waste water

6. Detach the dispenser cassettes around the peristaltic pumps

7. Incubator: turn off and have it slightly open for a while to let it cool down

## Update timings

1. Run a protocol which includes the timings you need

2. Use the log file to update the estimates json:

   ```
   cd robot-cellpainter
   cellpainter --add-estimates-from logs/2021-12-15_13:52:31-from-gui.jsonl
   ```

3. Use `git status` and `git diff` to see that it looks good!

4. Use `git add` and `git commit` and `git push` to commit and push it.
