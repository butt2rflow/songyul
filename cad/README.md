# v3 enclosure CAD

| Model | Contents | Default v3 mount |
| --- | --- | --- |
| `glove_case.scad` plus `glove_case_*.stl` | XIAO, LiPo, wake button, body, shelf and lid | Forearm, on a 22 mm quick-release watch band |
| `forearm_case.scad` plus `forearm_case_*.stl` | Adafruit LSM6DSOX breakout, body and lid | Back of the hand, on a hook-and-loop patch |

The filenames follow the earlier prototype. The firmware and analysis still interpret the XIAO as the **hand** sensor and the LSM6DSOX as the **forearm** sensor. To reproduce the current detector, mount the sensors in that order. The OpenSCAD mount parameters can be used to generate alternate mounting styles. Sensor role remapping for the v3 mounting positions remains to be validated.

Open the SCAD files in OpenSCAD. Select `part` for an individual piece. The `*_all.stl` exports place the parts together for printing. The combined controller export carries forward the v3 mesh cleanup. The standalone lid export also removes two coincident zero-area triangles from the CAD tessellation. Use the individual exports if you need to position parts separately.

Prototype settings were FDM, a 0.4 mm nozzle, 0.2 mm layers, and PLA or PETG. Check the USB-C, reset, LED and mic clearances on your first fit print. Several board feature positions were estimated from photos.

Songyul CAD uses [CC BY-NC-SA 4.0](../LICENSE-CAD-DOCS). Credit Songyul when sharing these models or adaptations.
