# imager standard operating protocol

The imager gui is at http://painter:3000 or equivalently http://10.10.0.55:3000
It can be reached from the Squid computer as well as the Nikon computer.
(technically it is running on the ubuntu NUC in the painter room)

Outline:

### Load the fridge

Use `fridge-load-from-hotel`. Specify a project name and the number of plates.
The barcode scanner will be used.

If it fails run `fridge-put` and enter the barcode manually. You can wiggle
it around the barcode reader to make it show up in the user interface.

Before starting:

* Make sure the following positions are free from plates:
1. fridge transfer station just in front of the barcode reader

* Locate the robotarm emergency stop button and put it where you can reach it
  - In doubt, stop the robot immediately using this button
  - Then press the stop button in the user interface



### Unloading the fridge

To unload the fridge use `fridge-unload` and pick up to 12 plates from the select box.

Before starting:

* Make sure the following positions are free from plates:
1. fridge transfer station just in front of the barcode reader
2. the target hotel locations

* Locate the robotarm emergency stop button and put it where you can reach it
  - In doubt, stop the robot immediately using this button
  - Then press the stop button in the user interface

### Showing fridge contents and entering plate metadata

Use `fridge-contents`.

You can use `add csv stubs to imager-fridge-metadata` to add to the network file share (nfs) directory.
It is mounted on the squid computer as `/mnt/imager-plate-metadata`.

Example: you just loaded two plates to the YM project. Press the `add csv stubs...` button and the `YM.csv`
file will be created with the following contents:

```
YM,PB900002,
YM,PB900003,
```

You can now add metadata by editing the file and saving it:

```
YM,PB900002,L1
YM,PB900003,L2
```

The columns are `project`, `barcode`, `metadata`. We will later use a fourth column to specify per-plate microscope settings.

Creating lines in the csv files and adding plate metadata is optional. Plates in the fridge without metadata can be acquired.

### Acquire using squid

Use `squid-acquire-from-fridge`. Specify a project in the auto-complete box, choose a protocol and RT time and the plates to image.
The selected images will be imaged in the order they appear in the select box. The order they appear in the select box can be
altered by rearranging the lines in the imager-plate-metadata csv files.

Before starting:

* Make sure the following positions are free from plates:
1. fridge transfer station just in front of the barcode reader
2. H12, the top location of the hotel
3. the squid stage

* Locate the robotarm emergency stop button and put it where you can reach it
  - In doubt, stop the robot immediately using this button
  - Then press the stop button in the user interface

The system does not have estimates for how long the acquisition will take which can make
the gui visualisation look weird. All is still OK: the robotarm system will still do run
the machines in the same sequential order.

#### Working remotely with one plate

If you just want a plate to the squid to work with it, you can use `fridge-unload` and then `H12-to-squid`. You can now work
with the plate in the squid user interface. Put it back with `squid-to-H12` and then `fridge-load-from-hotel`.

### Restarting from emergency stop

Rotate the emergency stop button so it releases.

Run the `pf-init` protocol. The robot gripper will open, very slowly, and then close again.

If it is holding a plate: be ready to catch it.

If it was holding a plate: run the pf-init once more without a plate, or it will be confused about how wide its grip is.

<img src='images/pf-init.png'>

### Moving the robot around: robot freedrive

The robotarm must be initialized (and emergency stop button must be released.)

If it is holding a plate: be ready to catch it. The gripper is released when starting robot freedrive.

Run the `pf-freedrive` protocol. When you're done press the stop button in the gui, go back and run `pf-stop-freedrive`.

<img src='images/pf-freedrive.png'>

<img src='images/pf-stop-freedrive.png'>

