# Standard operating procedure for robot-cellpainter

For dry runs.

For actual cell painting the protocol is similar but preparation and post-work
for washer, dispenser and incubator are more involved.

## Plate preparation

1. Put test plates in Virkon for a few hours

2. Prepare for --wash-plates-clean:

2.1 Put plates in A1, ...

2.2 Attach washer pump D to water from green tap

2.3 Attach washer pump C to ethanol

2.4 Attach washer waste bottle, preferably an empty one or one just used with water and ethanol

2.5 Prepare the robot as below

3. Run --wash-plates-clean

3. After wash-plates-clean:

3.1 Prime the washer tubes empty

3.2 Detach the washer waste bottle. If it contains only water and ethanol: empty it in the sink

3.3 Your plates are now safe!

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

## robotlab-ubuntu preparation

The robotlab-ubuntu computer is the NUC running ubuntu.

Log in as `pharmbio`, go to the directory for the repo, `~/robot-cellpainter/`.

1. Make sure you are running the desired version of the code. Use `git pull`, `git log`, `git status`, `git reset`, etc.

5. Start the gui:

   ```
   VIABLE_HOST=10.10.0.55 cellpainter-gui --live
   ```

## Robot arm preparation

Use the teach pendant.

1. Power on the robotarm

2. Activate the robot arm gripper

3. Move the robot arm to the neutral position (in front of the B21 hotel rack)

   With the teach pendant, hold down the freedrive button on the back side

4. Put the robot in remote mode

5. Put the teach pendant close to the keyboard so you can reach the emergency button

Now use `pharmbio@robotlab-ubuntu` the directory for the repo, `~/robot-cellpainter/`.

6. Run test communications to see that everything is communicating correctly:

   ```
   cellpainter --test-comm --live
   ```

   TODO: Add this to the gui

   TODO: Incubator get_climate reports success even though the incubator is off.

   If this fails make sure the robotlab-windows computer is running the
   labrobots server: https://github.com/pharmbio/robotlab-labrobots

7. Run the test circuit to see that everything is the correct place.

   Start with one plate with lid in the incubator transfer door.

   ```
   cellpainter --test-circuit --live
   ```

   TODO: Add this to the gui

   If not: move the instruments to their correct locations. If that is
   not possible update the locations using the `cellpainter-moves` program.

## Loading the incubator

1. Place the plates in A1, A2, ... They will be moved to L1, L2, ... inside the
   incubator. L1 is the first plate to be painted, L2 the second, and so on.

2. Make sure the robot is in neutral position (in front of the B21 hotel rack).

   Use the teach pendant and its freedrive button.

Now use `pharmbio@robotlab-ubuntu` in the directory for the repo, `~/robot-cellpainter/`.

3. Run the load incubator protocol with the correct amount of plates substituted:

   ```
   cellpainter --load-incu --num-plates $NUM_PLATES --live
   ```

   TODO: Add this to the gui

## Painting

1. Clean the robot gripper fingers so that they are free of dust.

2. Make sure the robot is in neutral position (in front of the B21 hotel rack)

   Use the teach pendant and its freedrive button.

3. Use the windows computer and go to http://10.10.0.55:5000.

4. Enter the desired settings

5. Press start

## After painting

1. If you want to store the log file (always do this for actual cell painting experiments),
   on the robot-ubuntu computer add the log file to git and push it:

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
