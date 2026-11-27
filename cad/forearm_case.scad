// 4438 IMU case. v3 (2026-11-14): the 4438 moves to the BACK OF THE HAND, held by a self-adhesive velcro patch on the
// flat base (mount = "velcro": no lugs, no flange); the XIAO case takes the forearm watch band. Cable end toward the wrist.
// Before: forearm IMU case on the glove's velcro strap. Draft 2026-11-02: outline, connector
// positions (centred on both short edges, flush with the edge) and LED read from reference photos on a ruler; component
// height (top_h) and PCB thickness are not measured yet, so check the first print.
// Two printed parts: the body (snug pocket with corner locators, open-top notch for the STEMMA QT plug + cable at one end,
// strain-relief pins, sewing flange with needle holes) and the lid (snap latch like the hand case, posts that press the
// board flat, an engraved arrow so the board always goes on the same way round).
// FDM, 0.4 mm nozzle, PLA or PETG, 0.2 mm layers, no supports (body open side up, lid flat side down).
//   part = "body" | "lid" | "snaptest" | "all" | "assembly"
part = "all";

// ---- board (MEASURE) ----
pcb     = [25.65, 17.75, 1.6]; // 25.63 x 17.73 mm measured 2026-11-02 (length = connector face to connector face; first reading 25.18, photo estimate 25.4 x 17.8)
                               // (2026-11-02), scaled by the 2.54 mm header pitch (9 holes = 20.32 mm); thickness not measured
under   = 0.8;                 // room under the board (header holes are unused; solder blobs, if any)
top_h   = 3.0;                 // tallest part on top: the STEMMA QT (JST SH) receptacles
plug    = [6.4, 3.8];          // STEMMA QT plug: width and height where it passes the end wall
plug_z  = 0.0;                 // plug bottom above the PCB top (side-entry receptacle: about level with the PCB top)
cable_d = 4.6;                 // cable exit notch width: the 4 STEMMA QT wires leave the plug side by side (~4 mm flat)
led     = [3.2, 12.6];         // power LED ("on", next to the cable-side connector) [mm from the cable end, mm from the left edge],
                               // from the photo, +-0.5 mm. Board lies in the case turned 180 deg from the photo (cable end at x = 0),
                               // so the silkscreen X arrow points along the lid arrow (+x, away from the cable)
led_hole = true;               // cone window over the power LED (2 -> 4 mm); position in "led" is a guess until the photo
chain   = false;               // false (2026-11-02): one cable at the MAIN end, far end closed -> shortest case. true: both ends open
//chain = true;                // STEMMA QT at BOTH ends: cable in at one end, out to the next sensor at the other (daisy chain)
labels  = false;               // off (2026-11-02): one opening + cable toward the hand fix the direction; the LED hole checks the connector
//labels = true;                // engrave "MAIN" (cable from the XIAO) and "OUT" (chain) at the two ends of the lid
arrow_x = false;               // off, same reason
//arrow_x = true;                // engrave an arrow on the lid pointing away from the cable end (match it to the silkscreen axes)

// ---- case ----
clr     = 0.3;
wall    = 1.6;
floor_t = 1.2;
lid_t   = 1.2;
corner_r = 2.0;
pin_d   = 3.0;
pins_len = 1.7;                // room at the cable end for the STEMMA QT plug: it sticks out 1.17 mm past the board
                               // (26.80 mm board + plug vs 25.63 board, 2026-11-02) + 0.5 mm
strain_pins = false;           // v1 draft had pins inside (9 mm per end); now a zip-tie tab outside each cable exit
loc     = [0.8, 0.2];          // corner locators: thickness, gap to the board
mount   = "velcro";            // v3: flat base for a velcro patch, on the back of the hand (2026-11-14)
//mount = "springbar";         // "springbar": watch lugs with spring-bar holes (2026-11-02, 22 mm quick-release band);
                               // "strap": fixed printed bars for NATO / single-pass straps; "flange": sewing flange
//mount = "strap";             // "strap": watch-strap bars on both long sides; "flange": sewing flange with needle holes
strap_w = 22.0;                // watch strap width (20 mm is the commonest; NATO or single-pass velcro)
strap_gap = 3.2;               // room for the strap between bar and case wall (NATO passes twice, ~1.3 mm per layer)
bar     = [3.0, 3.0];          // printed bar cross-section (out from the wall, height); prints flat on the bed
ear_t   = 2.0;                 // lug ear thickness along x
tie_tab = false;               // zip-tie tab outside the cable exit; off (2026-11-02): flush ends, cable held by the notch + lid
tie     = [1.6, 3.2];          // zip-tie slot in the tab outside each cable exit
flange  = 5.0;
hole_d  = 1.4;
snap    = true;
snap_d  = 0.8;                 // same as the hand case v2.2 (0.6 came loose after a few days); tune both from the snap tests
snap_l  = 8.0;                 // v2.2: was 6
nail    = [7.0, 1.0];

$fn = 40;
// Layout along x: cable end at x = 0 (pins area first, then the board); the far end wall is closed.
inner   = [pins_len * (chain ? 2 : 1) + pcb[0] + 2 * clr, pcb[1] + 2 * clr];
outer   = [inner[0] + 2 * wall, inner[1] + 2 * wall];
pcb_x   = wall + pins_len + clr;
pcb_y   = wall + clr;
z_pcb_bot = floor_t + under;
z_pcb_top = z_pcb_bot + pcb[2];
h_body  = z_pcb_top + top_h + clr;
snap_x  = pins_len + pcb[0] / 2;                     // bumps centred on the board's long sides
plug_y  = pcb_y + pcb[1] / 2;                        // receptacle centred on the short edge (check)

module rbox(s, h, r) { linear_extrude(h) offset(r) offset(-r) square(s); }

module snap_profile(side, d, len, top_z, is_groove) {
  y0 = side == 0 ? wall + clr : wall + inner[1] - clr;
  yw = side == 0 ? wall : wall + inner[1];
  yy = is_groove ? yw : y0;
  dir = side == 0 ? -1 : 1;
  z1 = top_z - 1.85; z2 = top_z - 0.75; z3 = top_z - 0.35;   // v2.2: peak raised, so the retaining face is ~63 deg (was ~40) and the entry ramp stays gentle
  translate([wall + snap_x - len / 2, yy, 0]) rotate([90, 0, 90]) linear_extrude(len)
    polygon(concat([[0, z1], [dir * d, z2], [0, z3]], is_groove ? [[-dir * 0.05, z3], [-dir * 0.05, z1]] : [[-dir * 0.3, z3], [-dir * 0.3, z1]]));
}

// cable exit through the end wall at x0 (outside face), open to the top; the lid closes it
module cable_notch(x0) {
  translate([x0 - 1, plug_y - cable_d / 2, z_pcb_top + plug_z + 0.4]) cube([wall + 2, cable_d, h_body]);
  translate([x0 - 1, plug_y, z_pcb_top + plug_z + 0.4 + cable_d / 2]) rotate([0, 90, 0]) cylinder(d = cable_d, h = wall + 2);
}
module strain_pins(x0, dir) {   // x0 = inside face of the end wall, dir = +1 going inward from x = 0, -1 from the far end
  for (i = [0:1]) translate([x0 + dir * (2.5 + i * 3.6), plug_y + (i == 0 ? -2.2 : 2.2), floor_t - 0.01]) cylinder(d = pin_d, h = h_body - floor_t - 0.4);
}

// Watch-strap lugs on both long sides: two ears and a fixed bar; the strap threads between the bar and the case wall.
// Spring-bar lugs: two ears per long side, 1.1 mm through-holes for the bar tips (~0.8 mm), strap_w + 0.2 between ears.
// The strap pull runs along the print layers (ears grow up from the bed), the strong direction.
sb_ear  = [2.6, 4.6, 5.0];     // ear: thickness along x, reach out from the wall, height (4.6: shortened 2026-11-02 for swing feel)
sb_hole = 1.1;                 // through-hole for the spring-bar tip; open with a 1 mm drill if it prints small
sb_out  = 2.6;                 // hole centre out from the case wall (room for the strap's end piece to turn)
sb_z    = 2.6;                 // hole centre height above the bed
module springbar_lugs() {
  xc = outer[0] / 2;
  gap = strap_w + 0.2;
  for (side = [0, 1]) {
    ys = side == 0 ? -sb_ear[1] : outer[1];
    yh = side == 0 ? -sb_out : outer[1] + sb_out;
    difference() {
      for (sx = [-1, 1]) translate([xc + sx * (gap / 2) + (sx < 0 ? -sb_ear[0] : 0), ys, 0])
        hull() {                                      // ear with a rounded outer end
          cube([sb_ear[0], 0.01 + (side == 0 ? sb_ear[1] - 1.5 : 1.5), sb_ear[2]]);
          translate([0, side == 0 ? 1.5 : sb_ear[1] - 1.5, 1.5]) rotate([0, 90, 0]) cylinder(r = 1.5, h = sb_ear[0]);
          translate([0, side == 0 ? 1.5 : sb_ear[1] - 1.5, sb_ear[2] - 1.5]) rotate([0, 90, 0]) cylinder(r = 1.5, h = sb_ear[0]);
          translate([0, side == 0 ? sb_ear[1] - 0.01 : 0, 0]) cube([sb_ear[0], 0.01, sb_ear[2]]);
        }
      translate([xc - gap / 2 - sb_ear[0] - 1, yh, sb_z]) rotate([0, 90, 0]) cylinder(d = sb_hole, h = gap + 2 * sb_ear[0] + 2, $fn = 24);
    }
  }
}

module strap_lugs() {
  xc = outer[0] / 2;
  reach = strap_gap + bar[0];
  ear_h = max(bar[1] + 1.0, 4.0);
  for (side = [0, 1]) {
    y0 = side == 0 ? -reach : outer[1];                       // outer edge of the lug zone
    for (sx = [-1, 1]) translate([xc + sx * (strap_w / 2 + 0.3) + (sx < 0 ? -ear_t : 0), y0, 0]) cube([ear_t, reach + 0.01, ear_h]);
    yb = side == 0 ? -reach : outer[1] + strap_gap;
    translate([xc - strap_w / 2 - 0.3 - ear_t, yb, 0]) cube([strap_w + 0.6 + 2 * ear_t, bar[0], bar[1]]);
  }
}
// Zip-tie tabs below each cable exit (the cable gets one tie here instead of weaving round pins inside)
module tie_tabs() {
  for (e = chain ? [0, 1] : [0]) {
    x0 = e == 0 ? -6 : outer[0];
    translate([x0, plug_y - 4, 0]) difference() {
      cube([6.01, 8, 1.6]);
      translate([(e == 0 ? 1.4 : 6 - 1.4 - tie[0]), 4 - tie[1] / 2, -1]) cube([tie[0], tie[1], 4]);
    }
  }
}

module body() {
  difference() {
    union() {
      rbox(outer, h_body, corner_r);
      if (mount == "flange") translate([-flange, -flange, 0]) rbox([outer[0] + 2 * flange, outer[1] + 2 * flange], 1.2, corner_r + flange);
    }
    translate([wall, wall, floor_t]) cube([inner[0], inner[1], h_body]);
    // cable exit: open-top notch in the cable-end wall, rounded bottom; the lid closes it
    cable_notch(0);
    if (chain) cable_notch(outer[0] - wall);
    if (snap) for (side = [0, 1]) snap_profile(side, snap_d + 0.1, snap_l + 0.6, h_body, true);
    translate([outer[0] - wall - 1, chain ? wall + 0.5 : outer[1] / 2 - nail[0] / 2, h_body - nail[1]]) cube([wall + 2, chain ? 4 : nail[0], nail[1] + 1]);
    if (mount == "flange") {
      for (x = [0, outer[0] / 2, outer[0]], y = [-flange / 2, outer[1] + flange / 2]) translate([x, y, -1]) cylinder(d = hole_d, h = 4);
      for (y = [outer[1] / 3, 2 * outer[1] / 3], x = [-flange / 2, outer[0] + flange / 2]) translate([x, y, -1]) cylinder(d = hole_d, h = 4);
    }
  }
  if (mount == "strap") { strap_lugs(); if (tie_tab) tie_tabs(); }
  if (mount == "springbar") { springbar_lugs(); if (tie_tab) tie_tabs(); }
  // board seat: two rails under the long edges (the middle stays clear)
  for (y = [pcb_y, pcb_y + pcb[1] - 1.5]) translate([pcb_x, y, floor_t - 0.01]) cube([pcb[0], 1.5, under + 0.01]);
  // corner locators at the four board corners
  lh = under + pcb[2] + 0.8;
  for (sx = [0, 1], sy = [0, 1]) {
    xx = sx == 0 ? pcb_x + 0.6 : pcb_x + pcb[0] - 1.8;
    yy = sy == 0 ? pcb_y - loc[1] - loc[0] : pcb_y + pcb[1] + loc[1];
    translate([xx, yy, floor_t - 0.01]) cube([1.2, loc[0], lh]);
  }
  // end stops (short, at the corners, clear of the receptacles in the middle of each short edge)
  for (xe = chain ? [pcb_x - loc[1] - loc[0], pcb_x + pcb[0] + loc[1]] : [pcb_x + pcb[0] + loc[1]], y = [pcb_y, pcb_y + pcb[1] - 2])
    translate([xe, y, floor_t - 0.01]) cube([loc[0], 2, lh]);
  // strain-relief pins between each cable exit and its plug: the cable weaves around them
  if (strain_pins) { strain_pins(wall, 1); if (chain) strain_pins(outer[0] - wall, -1); }
}

module lid() {
  difference() {
    union() {
      rbox(outer, lid_t, corner_r);
      // posts that press the board flat, near the two far corners (clear of the IMU chip in the middle)
      for (y = [pcb_y + 2.5, pcb_y + pcb[1] - 2.5]) translate([pcb_x + pcb[0] - 3.0, y, -(top_h + clr)]) cylinder(d = 2.6, h = top_h + clr + 0.01);
      // lip on the three closed sides
      translate([wall + clr, wall + clr, -2]) difference() {
        cube([inner[0] - 2 * clr, inner[1] - 2 * clr, 2]);
        translate([0.8, 0.8, -1]) cube([inner[0] - 2 * clr - 1.6, inner[1] - 2 * clr - 1.6, 4]);
      }
      if (snap) for (side = [0, 1]) snap_profile(side, snap_d, snap_l, 0, false);
    }
    translate([wall - 0.5, wall, -3]) cube([clr + 0.8 + 0.6, inner[1], 3]);   // no lip at the cable end(s)
    if (chain) translate([outer[0] - wall - clr - 0.8 - 0.1, wall, -3]) cube([clr + 0.8 + 0.6, inner[1], 3]);
    if (led_hole) translate([pcb_x + led[0], pcb_y + led[1], -0.01]) cylinder(d1 = 2.0, d2 = 4.0, h = lid_t + 0.02);
    // end labels, 0.4 mm deep, read across the lid: "MAIN" = the cable from the XIAO goes in here (connector next to the
    // board's "on" LED), "OUT" = the chained sensor
    if (labels) for (e = chain ? [[wall + pins_len / 2 + 1.5, "MAIN"], [outer[0] - wall - pins_len / 2 - 1.5, "OUT"]] : [[wall + 2.4, "MAIN"]])
      translate([e[0], chain ? outer[1] / 2 : wall + clr + 5.2, lid_t - 0.4]) rotate([0, 0, 90]) linear_extrude(1)   // single cable: beside the LED hole, not over it
        text(e[1], size = chain ? 3.0 : 2.6, font = "Liberation Sans:style=Bold", halign = "center", valign = "center");
    // arrow on the outside, 0.4 mm deep: points from the cable end toward the closed end
    if (arrow_x) translate([pcb_x + pcb[0] / 2 - 5, outer[1] / 2, lid_t - 0.4]) linear_extrude(1)
      polygon([[0, -0.8], [7, -0.8], [7, -2.4], [11, 0], [7, 2.4], [7, 0.8], [0, 0.8]]);
  }
}

if (part == "body") body();
else if (part == "lid") translate([0, 0, lid_t]) rotate([180, 0, 0]) translate([0, -outer[1], 0]) lid();
else if (part == "snaptest") {
  ring = 4;
  translate([0, 0, -(h_body - ring)]) intersection() { body(); translate([-20, -20, h_body - ring]) cube([200, 200, ring + 1]); }
  translate([outer[0] + 2 * flange + 4, outer[1], lid_t]) rotate([180, 0, 0]) lid();
}
else if (part == "all") { body(); translate([outer[0] + 2 * flange + 4, outer[1], lid_t]) rotate([180, 0, 0]) lid(); }
else if (part == "none") { }
else { body(); %translate([0, 0, h_body]) lid(); }

echo(str("forearm case outer ", outer[0], " x ", outer[1], " x ", h_body + lid_t, " mm (without the flange)"));
