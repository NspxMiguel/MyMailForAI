// swift-tools-version:5.9
import PackageDescription

let package = Package(
    name: "MyMailForAI",
    platforms: [.macOS(.v13)],
    targets: [
        .executableTarget(name: "MyMailForAI", path: "Sources/MyMailForAI")
    ]
)
