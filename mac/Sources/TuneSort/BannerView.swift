import AppKit
import SwiftUI
import TuneSortCore

/// The app's error banner: the message, plus what can be done about it.
struct BannerView: View {
    static let automationSettings =
        URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_Automation")!

    let banner: Banner
    let restart: () -> Void
    let dismiss: () -> Void

    /// osascript error -1743 ("Not authorized to send Apple events"): Automation was denied.
    private var isPermissionDenied: Bool {
        let m = banner.message.lowercased()
        return m.contains("-1743") || m.contains("not authorized")
    }

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle.fill")
                .foregroundStyle(.yellow)
            VStack(alignment: .leading, spacing: 6) {
                Text(banner.message)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
                if !banner.stderrTail.isEmpty {
                    ScrollView {
                        Text(banner.stderrTail.suffix(8).joined(separator: "\n"))
                            .font(.caption.monospaced())
                            .foregroundStyle(.secondary)
                            .textSelection(.enabled)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .frame(maxHeight: 110)
                }
                HStack {
                    switch banner.kind {
                    case .helperExited:
                        Button("Restart", action: restart)
                    case .music where isPermissionDenied:
                        Button("Open Automation Settings") {
                            NSWorkspace.shared.open(Self.automationSettings)
                        }
                    case .config:
                        SettingsLink { Text("Open Settings") }
                    default:
                        EmptyView()
                    }
                }
            }
            Spacer(minLength: 0)
            Button(action: dismiss) { Image(systemName: "xmark") }
                .buttonStyle(.borderless)
                .help("Dismiss")
        }
        .padding(10)
        .background(.yellow.opacity(0.15), in: RoundedRectangle(cornerRadius: 8))
        .overlay(RoundedRectangle(cornerRadius: 8).strokeBorder(.yellow.opacity(0.4)))
        .padding(.horizontal, 10)
        .padding(.top, 6)
    }
}
