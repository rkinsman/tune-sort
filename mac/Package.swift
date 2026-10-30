// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "TuneSort",
    platforms: [.macOS(.v14)],
    products: [
        .library(name: "TuneSortCore", targets: ["TuneSortCore"]),
        .executable(name: "TuneSort", targets: ["TuneSort"]),
    ],
    targets: [
        .target(name: "TuneSortCore"),
        .executableTarget(name: "TuneSort", dependencies: ["TuneSortCore"]),
        .testTarget(name: "TuneSortCoreTests", dependencies: ["TuneSortCore"]),
    ]
)
