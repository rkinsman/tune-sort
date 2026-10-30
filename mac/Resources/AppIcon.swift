// Draws the TuneSort app icon (playlist lines beside a tuning fork, on red) and writes
// AppIcon.icns. Regenerate after changing the drawing:
//
//     swift mac/Resources/AppIcon.swift mac/Resources
//
// Not part of the Swift package; AppIcon.svg is the same drawing for previewing.
import AppKit

func rgb(_ hex: Int) -> CGColor {
    NSColor(
        srgbRed: CGFloat((hex >> 16) & 0xFF) / 255, green: CGFloat((hex >> 8) & 0xFF) / 255,
        blue: CGFloat(hex & 0xFF) / 255, alpha: 1
    ).cgColor
}

/// Fills `clip` with a vertical gradient through `colors`, evenly spaced from `top` to
/// `bottom` (y grows downwards here).
func fillVertically(_ cg: CGContext, clip: CGPath, top: CGFloat, bottom: CGFloat, colors: [CGColor]) {
    let gradient = CGGradient(
        colorsSpace: CGColorSpace(name: CGColorSpace.sRGB), colors: colors as CFArray,
        locations: nil)!
    cg.saveGState()
    cg.addPath(clip)
    cg.clip()
    cg.drawLinearGradient(
        gradient, start: CGPoint(x: 0, y: top), end: CGPoint(x: 0, y: bottom), options: [])
    cg.restoreGState()
}

/// The macOS icon grid: a 1024 canvas with an 824 rounded square at 100, radius 185.
func drawIcon(size: CGFloat) -> NSBitmapImageRep {
    let px = Int(size)
    // Draw in sRGB, the space the Music colours were sampled in; a device-RGB bitmap would
    // shift them.
    let cg = CGContext(
        data: nil, width: px, height: px, bitsPerComponent: 8, bytesPerRow: 0,
        space: CGColorSpace(name: CGColorSpace.sRGB)!,
        bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue)!

    // Top-left origin, in 1024 units, so the coordinates match AppIcon.svg.
    cg.translateBy(x: 0, y: size)
    cg.scaleBy(x: size / 1024, y: -size / 1024)

    let shape = CGPath(
        roundedRect: CGRect(x: 100, y: 100, width: 824, height: 824),
        cornerWidth: 185, cornerHeight: 185, transform: nil)
    // The shadow, then the background: the Music app's red, a vertical gradient sampled
    // from its icon (#FF355D at the top, #FF1047 in the middle, #FF0030 at the bottom).
    cg.saveGState()
    cg.setShadow(
        offset: CGSize(width: 0, height: 10), blur: 28,
        color: NSColor.black.withAlphaComponent(0.3).cgColor)
    cg.addPath(shape)
    cg.setFillColor(rgb(0xFF0030))
    cg.fillPath()
    cg.restoreGState()
    fillVertically(cg, clip: shape, top: 100, bottom: 924,
                   colors: [rgb(0xFF355D), rgb(0xFF1047), rgb(0xFF0030)])

    // Concept A was drawn in a 120 box; k maps it onto the 824 square. The drawing spans
    // x 17...110.5 there, so dx shifts it left to leave equal margins (13.25) on both sides.
    let k: CGFloat = 824 / 120
    let dx: CGFloat = -3.75
    func p(_ x: CGFloat, _ y: CGFloat) -> CGPoint { CGPoint(x: 100 + (x + dx) * k, y: 100 + y * k) }

    // The list lines and the fork, filled as one shape so they share one gradient: white
    // shading to a faint pink at the bottom, like the note in the Music icon.
    let glyph = CGMutablePath()
    for (y, width) in [(28.0, 52.0), (46, 52), (64, 52), (82, 34)] {
        let rect = CGRect(origin: p(17, y), size: CGSize(width: width * k, height: 8 * k))
        glyph.addPath(CGPath(roundedRect: rect, cornerWidth: 4 * k, cornerHeight: 4 * k, transform: nil))
    }
    let fork = CGMutablePath()
    fork.move(to: p(84, 20))
    fork.addLine(to: p(84, 60))
    fork.addArc(
        center: p(95.5, 60), radius: 11.5 * k, startAngle: .pi, endAngle: 0, clockwise: true)
    fork.addLine(to: p(107, 20))
    fork.move(to: p(95.5, 72))
    fork.addLine(to: p(95.5, 102))
    glyph.addPath(fork.copy(strokingWithWidth: 7 * k, lineCap: .round, lineJoin: .round, miterLimit: 10))
    fillVertically(cg, clip: glyph, top: p(0, 16.5).y, bottom: p(0, 105.5).y,
                   colors: [rgb(0xFFFFFF), rgb(0xFFFFFF), rgb(0xFFD4DE)])

    let rep = NSBitmapImageRep(cgImage: cg.makeImage()!)
    rep.size = NSSize(width: size, height: size)
    return rep
}

let outDir = URL(fileURLWithPath: CommandLine.arguments.count > 1 ? CommandLine.arguments[1] : ".")
let iconset = FileManager.default.temporaryDirectory
    .appendingPathComponent("AppIcon-\(ProcessInfo.processInfo.processIdentifier).iconset")
try? FileManager.default.removeItem(at: iconset)
try FileManager.default.createDirectory(at: iconset, withIntermediateDirectories: true)

for base in [16, 32, 128, 256, 512] {
    for scale in [1, 2] {
        let name = scale == 1 ? "icon_\(base)x\(base).png" : "icon_\(base)x\(base)@2x.png"
        let data = drawIcon(size: CGFloat(base * scale)).representation(using: .png, properties: [:])!
        try data.write(to: iconset.appendingPathComponent(name))
    }
}

let icns = outDir.appendingPathComponent("AppIcon.icns")
let iconutil = Process()
iconutil.executableURL = URL(fileURLWithPath: "/usr/bin/iconutil")
iconutil.arguments = ["-c", "icns", iconset.path, "-o", icns.path]
try iconutil.run()
iconutil.waitUntilExit()
try? FileManager.default.removeItem(at: iconset)
guard iconutil.terminationStatus == 0 else {
    FileHandle.standardError.write("iconutil failed\n".data(using: .utf8)!)
    exit(1)
}
print("Wrote \(icns.path)")
