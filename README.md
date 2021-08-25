# robotlab-labrobots

Web servers to our LiCONiC incubator and BioTek washer and dispenser.

This provides a unified http api to all robots in the AROS system,
Open Automated Robotic System for Biological Laboratories, https://github.com/pharmbio/aros.
The http api wraps around vendor-specific api:s for communication.

<table>
<tr>
<td>LiCONiC incubator</td>
<td><img height=400 src=images/STX_44_BT_Flush_Front_new-tm.jpg></td>
</tr>
<tr>
<td>BioTek washer</td>
<td><img width=329 src=images/biotek-405-washer.jpg></td>
</tr>
<tr>
<td>BioTek dispenser</td>
<td><img width=329 src=images/biotek-dispenser.jpg></td>
</tr>
</table>

The setup is outlined in the schematic below, which indicates the
purpose of the three subdirectories in this repo, `biotek-cli/`, `biotek-server/` and `incubator-server/`.

<img src=images/overview.svg>

Since we have a C# program we will need to use a windows machine.
For simplicity, we run everything on the same windows machine.
