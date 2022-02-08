# Standard operating procedure for robot-cellpainter

## Incubator preparation

1. Turn on incubator

2. Ensure it is clean

3. Give it enough water to stay humid

## Washer preparation

1. Turn on washer

2. Attach PBS to pump D

   If dry run: attach water from green tap to pump D

3. Attach the waste bottle

## Dispenser preparation

1. Turn on dispenser

2. Attach the correct liquids

   If dry run: run either with air or with water from green tap

3. Attach the waste bottle

   If dry run and running with air: skip

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

   TODO: Incubator get climate reports success even though the incubator is off.

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

1. Use the windows computer and go to http://10.10.0.55:5000.

2. Make sure the robot is in neutral position (in front of the B21 hotel rack)

   Use the teach pendant and its freedrive button.

3. Enter the desired settings

4. Press start

## After painting

1. On the robot-ubuntu computer add the log file to git and push it:

```
cd robot-cellpainter
git add --force logs/2021-12-15_13:52:31-from-gui.jsonl
git push
```

2. Put the robot arm in local (not in remote) using the teach pendant
