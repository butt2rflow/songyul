// Songyul v3 controller case, stacked: 350 mAh LiPo at the bottom, XIAO nRF52840 Sense on top, wake button beside it.
// Three printed parts: the body (pocket + open-top USB-C / cable notches + watch-band lugs), the shelf plate that drops in on
// top of the battery (posts + corner locators for the XIAO, the wake-button pocket, strain-relief pins, a lead channel along
// one side), and the lid (RST tab, wake-button tab, LED / mic holes, a post that presses the board).
// Assembly: battery in (leads on the channel side), shelf on it, button into its pocket, XIAO into its corners, lid on.
// FDM, 0.4 mm nozzle, PLA or PETG, 0.2 mm layers, no supports (body open side up, shelf flat, lid flat side down).
// What the first fit print taught (Ender-3 Pro, 2026-10-31): the USB-C window with 0.4 mm above it
// closed up and the board sat high -> open-top notch, receptacle flush with the outside; the lid lip hit the USB-C ->
// cut out there; the XIAO slid sideways -> corner locators; the lead notch in the middle was out of reach of the battery's
// corner leads -> channel along the whole side; 2.4 mm posts and 2.2 mm pins melted into blobs -> 3 mm; the button fits a
// 6.1 mm pocket best (6.1 and 6.3 both held, 6.1 clicked cleaner).
// v3 (2026-11-14): the XIAO case moves to the forearm on the 22 mm quick-release watch band (the 4438 goes on the
// back of the hand on velcro). The sewing flange is gone; spring-bar lugs on both long sides instead (mount = "springbar",
// same lugs as forearm_case.scad). Wear it with the USB-C / cable end toward the hand. mount = "flange" brings v2.2 back.
// v2.2 (2026-11-13): firmer snap (the lids popped open on a light knock after a few days): catch 0.3 -> 0.5 mm per side,
// steeper retaining face, 8 mm bumps. Open with the fingernail notch.
// v2.1 (2026-11-02): snap latch. Ramped bumps on the outside of the lid lip's two long sides click into grooves in the
// body's inner walls; a fingernail notch in the body rim at the far end lifts the lid. "snaptest" prints only the top
// ring of the body plus the lid, to tune snap_d before reprinting the whole case.
//   part = "body" | "shelf" | "lid" | "test" (wake-button test strip) | "snaptest" | "all" (body + shelf + lid, one print) | "assembly"
part = "all";

// ---- parts (measure and correct) ----
bat   = [30.0, 25.0, 5.5];     // LiPo as placed: length x width x thickness
xiao  = [21.0, 17.8, 1.0];     // XIAO board outline and PCB thickness
xiao_under = 2.0;              // room under the board: on the glove the power and ground wires and glue sit on the back
posts = [[2.5, 15.3], [19.0, 2.5], [19.0, 15.3]];   // board support points [from USB end, from left], clear of the back's wires
post_d = 3.0;
xiao_top   = 3.4;              // tallest part on top: the USB-C receptacle (~3.2 mm)
usb   = [9.6, 3.6];            // USB-C receptacle notch width, and the receptacle height
// Positions on the board's TOP side, seen from above with the USB-C at the top: [mm from the USB end, mm from the left edge].
// Read off a reference photo (2026-10-28, ~16.3 px/mm); +-1 mm.
usb_over = 1.6;                // the USB-C receptacle sticks out past the board's USB edge
rst   = [1.5, 2.8];            // RST button (left of the USB-C)
led   = [1.2, 14.1];           // user LED (right of the USB-C, "USR")
mic_on_back = false;
mic   = [19.1, 14.4];          // PDM mic sound hole
can   = [12.5, 8.9, 2.0];      // centre of the shield can and its height above the PCB: the lid's post presses here
rst_h = 1.0;                   // RST button top above the PCB
tongue = [10.0, 0.6];          // RST tongue length and thickness (strain ~0.45 % at 0.5 mm bend)
led_style = "cone";            // "cone": 2 -> 4 mm hole, any filament; "thin": 0.4 mm window (white / natural filament only)

// wake button: 6 x 6 tact switch (DAOKI), stands on the shelf beyond the board's far end, plunger up under a lid tab.
// Legs: cut the two unused ones short and bend the two diagonal ones out flat through the wall notches (never down: the
// battery is right under the shelf). Wires from them to D2 and GND.
sw      = 6.1;                 // pocket inside (test strip 2026-10-31)
sw_h    = 4.3;                 // switch bottom to plunger top
sw_wall = 2.6;                 // pocket wall height (the switch body is ~3.5 mm)
sw_leg  = [4.5, 1.4];          // leg pair spacing across the notched walls, notch width
btab    = [9.0, 5.0];          // lid tab over the button: length (hinge side toward +y) and width; wider than the RST tab

// ---- case ----
clr   = 0.3;                   // fit clearance on each side
wall  = 1.6;
floor_t = 1.2;                 // bottom under the battery
shelf_t = 1.0;                 // plate between battery and XIAO
lid_t = 1.2;
corner_r = 2.0;
cable_d = 2.8;                 // STEMMA QT cable (~2.5 mm jacket), leaves at the USB end toward the wrist
pin_d   = 3.0;                 // strain-relief pins
chan_w  = 2.3;                 // battery-lead channel along the -y side of the shelf
loc     = [0.8, 0.2];          // XIAO corner locators: thickness, gap to the board
mount  = "springbar";         // "springbar": watch lugs for a 22 mm quick-release band (v3, 2026-11-14); "flange": v2.2 sewing flange
strap_w = 22.0;                // watch band width
flange = 5.0;                  // sewing flange around the base (mount = "flange" only)
hole_d = 1.4;                  // needle holes in the flange
// snap latch
snap    = true;
snap_d  = 0.8;                 // bump height past the lip face; the lip has clr (0.3) of play, so 0.8 = 0.5 mm of catch per side (v2.2; 0.6 came loose after a few days)
snap_l  = 8.0;                 // bump length along the wall (v2.2: was 6)
snap_x  = 12.0;                // bump centre from the USB-end inner wall: over the XIAO, clear of the cable pins near the far end
nail    = [7.0, 1.0];          // fingernail notch in the body rim at the far end: width, depth

$fn = 40;
// Layout along x: the XIAO's USB edge sits 0.1 mm from the end wall's inside at x = 0 (wrist side), so the receptacle
// (usb_over past the board) fills the wall's open-top notch and ends flush with the outside: the plug's shell reaches it
// and its overmould stays outside. Beyond the board's far end: the button pocket (centre) and the cable pins (+y side).
xiao_x = wall + 0.1;
sw_o   = sw + 2.4;                                   // button pocket outside
inner  = [max(bat[0] + 2 * clr, xiao_x - wall + xiao[0] + 1 + sw_o + 1.5), max(bat[1], xiao[1]) + 2 * clr];
xiao_y = wall + clr + (inner[1] - 2 * clr - xiao[1]) / 2;
z_bat_top  = floor_t + bat[2] + clr;
z_shelf_top = z_bat_top + shelf_t;
z_pcb_bot  = z_shelf_top + xiao_under;
z_pcb_top  = z_pcb_bot + xiao[2];
h_body     = z_pcb_top + xiao_top + clr;          // the lid sits on top of this
outer = [inner[0] + 2 * wall, inner[1] + 2 * wall];
sw_c  = [xiao_x + xiao[0] + 1 + sw_o / 2, wall + clr + chan_w + 0.6 + sw_o / 2];   // button centre (x, y)
cab_y = wall + inner[1] - cable_d / 2 - 1.0;        // cable path along the +y side

module rbox(s, h, r) { linear_extrude(h) offset(r) offset(-r) square(s); }

// Ramped bump (lid) or groove (body) on a long side. Profile across the wall: slope in from the bottom, gentler slope out
// at the top, so it clicks shut and can be pried open. top_z = the body rim; the lip occupies top_z - 2 .. top_z.
module snap_profile(side, d, len, top_z, is_groove) {
  y0 = side == 0 ? wall + clr : wall + inner[1] - clr;     // lip outer faces
  yw = side == 0 ? wall : wall + inner[1];                 // body inner walls
  yy = is_groove ? yw : y0;
  dir = side == 0 ? -1 : 1;
  z1 = top_z - 1.85; z2 = top_z - 0.75; z3 = top_z - 0.35;   // v2.2: peak raised, so the retaining face is ~63 deg (was ~40) and the entry ramp stays gentle  // bottom of ramp, peak, top of ramp
  translate([wall + snap_x - len / 2, yy, 0]) rotate([90, 0, 90]) linear_extrude(len)
    polygon(concat([[0, z1], [dir * d, z2], [0, z3]], is_groove ? [[-dir * 0.05, z3], [-dir * 0.05, z1]] : [[-dir * 0.3, z3], [-dir * 0.3, z1]]));
}

module body() {
  difference() {
    union() {
      rbox(outer, h_body, corner_r);
      if (mount == "flange") translate([-flange, -flange, 0]) rbox([outer[0] + 2 * flange, outer[1] + 2 * flange], 1.2, corner_r + flange);   // sewing flange
    }
    translate([wall, wall, floor_t]) cube([inner[0], inner[1], h_body]);
    // USB-C: notch open to the top (nothing to bridge, forgiving in height); the lid closes it
    translate([-1, xiao_y + xiao[1] / 2 - usb[0] / 2, z_pcb_top - 0.4]) cube([wall + 2, usb[0], h_body]);
    // STEMMA cable: notch open to the top, same wall, rounded bottom
    translate([-1, cab_y - cable_d / 2, z_pcb_top + 0.6]) cube([wall + 2, cable_d, h_body]);
    translate([-1, cab_y, z_pcb_top + 0.6]) rotate([0, 90, 0]) cylinder(d = cable_d, h = wall + 2);
    // snap grooves in both long inner walls, matching the lid bumps (lip spans h_body - 2 .. h_body)
    if (snap) for (side = [0, 1]) snap_profile(side, snap_d + 0.1, snap_l + 0.6, h_body, true);
    // fingernail notch to lift the lid, far end
    translate([outer[0] - wall - 1, outer[1] / 2 - nail[0] / 2, h_body - nail[1]]) cube([wall + 2, nail[0], nail[1] + 1]);
    // needle holes in the flange
    if (mount == "flange") {
      for (x = [0, outer[0] / 2, outer[0]], y = [-flange / 2, outer[1] + flange / 2]) translate([x, y, -1]) cylinder(d = hole_d, h = 4);
      for (y = [outer[1] / 3, 2 * outer[1] / 3], x = [-flange / 2, outer[0] + flange / 2]) translate([x, y, -1]) cylinder(d = hole_d, h = 4);
    }
  }
  if (mount == "springbar") springbar_lugs();
}

// Spring-bar lugs on both long sides (copied from forearm_case.scad, worn there since 2026-11-04): two ears per side,
// 1.1 mm through-holes for the bar tips, strap_w + 0.2 between the ears. The band pull runs along the print layers.
sb_ear  = [2.6, 4.6, 5.0];     // ear: thickness along x, reach out from the wall, height
sb_hole = 1.1;                 // spring-bar tip hole; open with a 1 mm drill if it prints small
sb_out  = 2.6;                 // hole centre out from the case wall
sb_z    = 2.6;                 // hole centre height above the bed
module springbar_lugs() {
  xc = outer[0] / 2;
  gap = strap_w + 0.2;
  for (side = [0, 1]) {
    ys = side == 0 ? -sb_ear[1] : outer[1];
    yh = side == 0 ? -sb_out : outer[1] + sb_out;
    difference() {
      for (sx = [-1, 1]) translate([xc + sx * (gap / 2) + (sx < 0 ? -sb_ear[0] : 0), ys, 0])
        hull() {
          cube([sb_ear[0], 0.01 + (side == 0 ? sb_ear[1] - 1.5 : 1.5), sb_ear[2]]);
          translate([0, side == 0 ? 1.5 : sb_ear[1] - 1.5, 1.5]) rotate([0, 90, 0]) cylinder(r = 1.5, h = sb_ear[0]);
          translate([0, side == 0 ? 1.5 : sb_ear[1] - 1.5, sb_ear[2] - 1.5]) rotate([0, 90, 0]) cylinder(r = 1.5, h = sb_ear[0]);
          translate([0, side == 0 ? sb_ear[1] - 0.01 : 0, 0]) cube([sb_ear[0], 0.01, sb_ear[2]]);
        }
      translate([xc - gap / 2 - sb_ear[0] - 1, yh, sb_z]) rotate([0, 90, 0]) cylinder(d = sb_hole, h = gap + 2 * sb_ear[0] + 2, $fn = 24);
    }
    // root blocks 0.5 mm into the wall, so each ear is one solid with the body (touching faces exported as separate shells)
    for (sx = [-1, 1]) translate([xc + sx * (gap / 2) + (sx < 0 ? -sb_ear[0] : 0), side == 0 ? -0.6 : outer[1] - 0.5, 0]) cube([sb_ear[0], 1.1, sb_ear[2]]);
  }
}

// Drops in on top of the battery (printed flat).
module shelf() {
  // plate, minus the lead channel along the whole -y side (the battery's corner leads come up wherever they leave it)
  translate([wall + clr, wall + clr + chan_w, z_bat_top]) cube([inner[0] - 2 * clr, inner[1] - 2 * clr - chan_w, shelf_t]);
  // posts under the board
  for (p = posts) translate([xiao_x + p[0], xiao_y + p[1], z_shelf_top - 0.01]) cylinder(d = post_d, h = xiao_under + 0.01);
  // corner locators: the board drops between them and can't slide; only at the corners, clear of the edge pads
  lh = xiao_under + xiao[2] + 0.8;
  g = loc[1]; t = loc[0];
  for (sy = [0, 1]) {
    yy = sy == 0 ? xiao_y - g - t : xiao_y + xiao[1] + g;
    for (xx = [xiao_x + 0.4, xiao_x + xiao[0] - 1.6])            // along the long edges, 1.2 mm long, at both ends
      translate([xx, yy, z_shelf_top - 0.01]) cube([1.2, t, lh]);
    // far end: short-edge stop
    translate([xiao_x + xiao[0] + g, sy == 0 ? xiao_y - g - t : xiao_y + xiao[1] - 2.5, z_shelf_top - 0.01]) cube([t, 2.5 + g + t, lh]);
  }
  // wake-button pocket
  translate([sw_c[0] - sw_o / 2, sw_c[1] - sw_o / 2, z_shelf_top - 0.01]) difference() {
    cube([sw_o, sw_o, sw_wall + 0.01]);
    translate([1.2, 1.2, -1]) cube([sw, sw, sw_wall + 2]);
    // notches for the legs in the two walls facing +-x
    for (y = [-sw_leg[0] / 2, sw_leg[0] / 2]) translate([-1, sw_o / 2 + y - sw_leg[1] / 2, -1]) cube([sw_o + 2, sw_leg[1], sw_wall + 2]);
  }
  // strain-relief pins on the +y side beyond the board: the cable weaves around them before its pads
  for (i = [0:2]) translate([xiao_x + xiao[0] + 2.2 + i * 3.4, cab_y + (i % 2 == 0 ? -1.9 : 0.6), z_shelf_top - 0.01])
    cylinder(d = pin_d, h = h_body - z_shelf_top - 0.4);
}

module lid() {
  sw_top = z_shelf_top + sw_h;                     // plunger top
  bnub = h_body - sw_top - 0.2;                    // nub length under the button tab
  union() {
  difference() {
    union() {
      rbox(outer, lid_t, corner_r);
      // post down onto the shield can: holds the board so the hand IMU can't rattle
      translate([xiao_x + can[0], xiao_y + can[1], -(xiao_top + clr - can[2])]) cylinder(d = 4, h = xiao_top + clr - can[2] + 0.01);
      // snap bumps on the lip's long outer faces (lid coordinates: lid bottom = 0, so top_z = 0)
      if (snap) for (side = [0, 1]) snap_profile(side, snap_d, snap_l, 0, false);
      // lip that drops into the opening (press fit)
      translate([wall + clr, wall + clr, -2]) difference() {
        cube([inner[0] - 2 * clr, inner[1] - 2 * clr, 2]);
        translate([0.8, 0.8, -1]) cube([inner[0] - 2 * clr - 1.6, inner[1] - 2 * clr - 1.6, 4]);
      }
    }
    // no lip along the USB end at all (v1's lip hit the receptacle; the RST tab and LED sit there too): lip on 3 sides
    translate([wall - 0.5, wall, -3]) cube([clr + 0.8 + 0.6, inner[1], 3]);
    // RST: U-slot tongue, thinned from the inside (the outside half prints flat on the bed)
    translate([xiao_x + rst[0], xiao_y + rst[1], 0]) {
      for (y = [-2.3, 1.7]) translate([-2.1, y, -3]) cube([tongue[0] + 0.6, 0.6, 6]);
      translate([-2.1, -2.3, -3]) cube([0.6, 4.6, 6]);
      translate([-1.5, -1.7, -1]) cube([tongue[0], 3.4, 1 + lid_t - tongue[1]]);
    }
    // wake button: wider U-slot tongue along +y, free end over the plunger
    translate([sw_c[0], sw_c[1], 0]) {
      for (x = [-btab[1] / 2 - 0.6, btab[1] / 2]) translate([x, -2.1, -3]) cube([0.6, btab[0] + 0.6, 6]);
      translate([-btab[1] / 2 - 0.6, -2.1, -3]) cube([btab[1] + 1.2, 0.6, 6]);
      translate([-btab[1] / 2, -1.5, -1]) cube([btab[1], btab[0], 1 + lid_t - tongue[1]]);
    }
    // LED and mic
    if (led_style == "cone") translate([xiao_x + led[0], xiao_y + led[1], -0.01]) cylinder(d1 = 2.0, d2 = 4.0, h = lid_t + 0.02);
    else translate([xiao_x + led[0], xiao_y + led[1], 0.4]) cylinder(d = 4.0, h = lid_t);
    if (!mic_on_back) translate([xiao_x + mic[0], xiao_y + mic[1], -3]) cylinder(d = 2.0, h = 6);
  }
  // nubs, added after the cuts: RST stops 0.3 mm above its button, the wake nub 0.2 mm above the plunger
  translate([xiao_x + rst[0], xiao_y + rst[1], -(xiao_top + clr - rst_h - 0.3)]) cylinder(d = 1.6, h = xiao_top + clr - rst_h - 0.3 + lid_t - tongue[1] + 0.01);
  translate([sw_c[0], sw_c[1], -bnub]) cylinder(d = 3.0, h = bnub + lid_t - tongue[1] + 0.01);
  }
}

// Wake-button test strip (v1 test, kept for other switches): pockets 6.1 / 6.3 / 6.5 mm (1 / 2 / 3 dots), each with a tongue.
sw_sizes = [6.1, 6.3, 6.5];
sw_depth = 5.0;
module button_test() {
  pitch = 12;
  union() {
  difference() {
    union() {
      cube([pitch * len(sw_sizes) + 4, 10, lid_t]);   // +4: the last tongue's hinge stays on the plate (v1 lost it)
      for (i = [0:len(sw_sizes) - 1]) translate([1 + i * pitch, 0, 0]) {
        s = sw_sizes[i];
        translate([(pitch - 1 - s) / 2 - 1.2, 5 - s / 2 - 1.2, lid_t - 0.01]) difference() {
          cube([s + 2.4, s + 2.4, sw_depth + 0.01]);
          translate([1.2, 1.2, -1]) cube([s, s, sw_depth + 2]);
          for (y = [-sw_leg[0] / 2, sw_leg[0] / 2]) translate([-1, 1.2 + s / 2 + y - sw_leg[1] / 2, -1]) cube([s + 4.4, sw_leg[1], sw_depth + 2]);
        }
      }
    }
    for (i = [0:len(sw_sizes) - 1]) translate([1 + i * pitch + (pitch - 1) / 2, 5, 0]) {
      for (y = [-2.3, 1.7]) translate([-2.1, y, -1]) cube([tongue[0] - 1.5 + 0.6, 0.6, lid_t + 2]);
      translate([-2.1, -2.3, -1]) cube([0.6, 4.6, lid_t + 2]);
      translate([-1.5, -1.7, tongue[1]]) cube([tongue[0] - 1.5, 3.4, lid_t - tongue[1] + 0.01]);
      translate([sw_sizes[0] / 2 - 0.05, -2.0, lid_t]) cube([tongue[0], 4.0, sw_depth + 1]);
      for (k = [0:i]) translate([-3.5 + k * 1.5, -4, -0.01]) cylinder(d = 0.9, h = 0.4);
    }
  }
  for (i = [0:len(sw_sizes) - 1]) translate([1 + i * pitch + (pitch - 1) / 2, 5, tongue[1] - 0.01]) cylinder(d = 2.4, h = lid_t - tongue[1] + sw_depth - sw_h - 0.2 + 0.01);
  }
}

if (part == "body") body();
else if (part == "shelf") translate([0, 0, -z_bat_top]) shelf();
else if (part == "test") button_test();
else if (part == "lid") translate([0, 0, lid_t]) rotate([180, 0, 0]) translate([0, -outer[1], 0]) lid();
else if (part == "all") {
  body();
  translate([outer[0] + 2 * flange + 4, 0, -z_bat_top]) shelf();
  translate([2 * (outer[0] + 2 * flange + 4), outer[1], lid_t]) rotate([180, 0, 0]) lid();
}
else if (part == "snaptest") {
  ring = 4;                                        // top 4 mm of the body walls, upside-free: printed open side up
  translate([0, 0, -(h_body - ring)]) intersection() { body(); translate([-20, -20, h_body - ring]) cube([200, 200, ring + 1]); }
  translate([outer[0] + 6, outer[1], lid_t]) rotate([180, 0, 0]) lid();
}
else if (part == "none") { }   // for files that include this one (assembly_steps.scad)
else { body(); color("orange") shelf(); %translate([0, 0, h_body]) lid(); }

echo(str("outer ", outer[0], " x ", outer[1], " x ", h_body + lid_t, " mm (without flange/lugs; mount ", mount, "); button nub ", h_body - z_shelf_top - sw_h - 0.2, " mm"));
