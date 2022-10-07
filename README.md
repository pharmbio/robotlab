# robotlab

This is the monorepo for the robots in our robotlabs.
It consists of three packages:

<table>

<tr>
<th>labrobots</th>
<td>
Remote control of non-robotarm robots: liquid handling machines from BioTek, incubator and fridge from Liconic, microscope and barcode scanner.
</td>
</tr>

<tr>
<th>cellpainter</th>
<td>
Cell painter program and control of the Universal Robot (UR) robotarm.
</td>
</tr>

<tr>
<th>imager</th>
<td>
Microscope imager program and control of the the PreciseFlex (PF) robotarm.
</td>
</tr>

</table>

External dependencies:

<table>

<tr>
<td>flask</td>
<td>
Micro framework for building web applications.
</td>
</tr>

<tr>
<td>z3-solver</td>
<td>
SMT-solver used in the cellpainter scheduler.
</td>
</tr>

<tr>
<td>apsw</td>
<td>
Another python sqlite3 wrapper, needed for precise control of sqlite3 version. We need all json extensions.
</td>
</tr>

<tr>
<td>pyserial</td>
<td>
COM-port communication for communication with IMX and barcode scanner.
</td>
</tr>

</table>

The BioTek control code require a C# program that needs to be separately built.

## Installation

On the ubuntu NUC that will run all schedulers, install python >= 3.10 and then:

```
./foreach.sh pip install --editable
```

On each windows machine that runs labrobots, install python >= 3.8 and:

```
pip install --editable labrobots
```

