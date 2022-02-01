# imx-pharmbio-automation

Control of the PreciseFlex (PF) robotarm and the MolDev ImageXpress (IMX) microscope.

A scheduler repeatedly talks to the PF and the IMX to keep them busy.

A human operator can add entries to the scheduler.

<img src="images/overview.svg"/>

### IP numbers

ip           | computer
---          | ---
`10.10.0.99` | IMX Windows computer
`10.10.0.98` | PreciseFlex robotarm
`10.10.0.97` | "GBG" Windows computer
`10.10.0.55` | robotlab ubuntu nuc

