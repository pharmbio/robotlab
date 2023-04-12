# robotlab

This is the monorepo for the robots in our robotlabs.
It consists of three packages:

<table>

<tr>
<th>cellpainter</th>
<td>
Cell painter program and control of the Universal Robot (UR) robotarm.
Microscope imager program and control of the PreciseFlex (PF) robotarm.
</td>
</tr>

<tr>
<th>labrobots</th>
<td>
Remote control of non-robotarm robots: liquid handling machines, incubator, fridge, microscopes and barcode scanners.
</td>
</tr>

<tr>
<th>flash_pf</th>
<td>
Code to flash the PreciseFlex (PF) robotarm with our modified software.
</td>
</tr>


</table>

It also includes two utility packages:

<table>

<tr>
<th>viable</th>
<td>
Library for writing web frontend code in python.
</td>
</tr>

<tr>
<th>pbutils</th>
<td>
Shared utilities such as bridging dataclasses and sqlite3.
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
SMT-solver used in the robotlab scheduler.
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
COM-port communication with IMX and barcode scanner.
</td>
</tr>

</table>

The BioTek control code require a C# program that needs to be separately built.

## Installation

On the ubuntu NUC that will run the guis and schedulers, install python >= 3.10 and then:

```
./foreach.sh pip install --editable .
```

On each windows machine that runs labrobots, install python >= 3.8 and:

```
pip install --editable labrobots
```

Further instructions are in under [`labrobots/`](labrobots/README.md)

## Test

Github actions is set up, check [`.github/workflows/test.yml`](.github/workflows/test.yml).
One way to run this locally is to use [`act`](https://github.com/nektos/act).

## Network setup

The node names and IP-addresses are specified in [`labrobots/labrobots/__init__.py`](labrobots/labrobots/__init__.py).

## Git diff of sqlite databases

To enable showing diffs of sqlite databases when running git commands you can follow https://stackoverflow.com/questions/13271643/git-hook-for-diff-sqlite-table

One way to ignore big blobs is adding this to git config:

    [diff "sqlite3"]
        binary = true
        textconv = "dump(){ sqlite3 -batch \"$1\" .dump | sed \"s,X'\\([0-9a-f]\\{16\\}\\)[0-9a-f]*',X'\\1...',g\"; }; dump"

You will need to add this to git attributes:

    *.db diff=sqlite3
