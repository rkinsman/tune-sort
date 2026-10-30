import SwiftUI
import TuneSortCore

/// The window's root: the app once the helper is up, otherwise why it isn't.
struct RootView: View {
    let state: AppState

    var body: some View {
        Group {
            switch state.phase {
            case .starting:
                ProgressView("Starting the helper…")
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
            case .ready(let session):
                AppView(session: session, restart: { Task { await state.restart() } })
            case .setup(let path):
                SetupView(state: state, path: path)
            case .mismatch(let message):
                ContentUnavailableView {
                    Label("Wrong helper version", systemImage: "exclamationmark.triangle")
                } description: {
                    Text(message)
                }
            case .failed(let message, let tail):
                StartFailedView(state: state, message: message, stderrTail: tail)
            }
        }
        .frame(minWidth: 800, minHeight: 480)
        .task { await state.startIfNeeded() }
    }
}

/// Shown when the helper executable is missing: the path tried, how to install it, and
/// the repo path to look in.
struct SetupView: View {
    @Bindable var state: AppState
    let path: String

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label("TuneSort can't find its helper", systemImage: "wrench.and.screwdriver")
                .font(.title2.weight(.semibold))
            VStack(alignment: .leading, spacing: 4) {
                Text("Looked for:").foregroundStyle(.secondary)
                Text(path).font(.body.monospaced()).textSelection(.enabled)
            }
            Text("Run `uv sync` in the repo to install it, then try again.")
            RepoPathField(state: state)
            Button("Try Again") { Task { await state.restart() } }
                .keyboardShortcut(.defaultAction)
        }
        .padding(32)
        .frame(maxWidth: 560)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

/// Shown when the helper exists but didn't say hello (it crashed, or isn't the helper).
struct StartFailedView: View {
    @Bindable var state: AppState
    let message: String
    let stderrTail: [String]

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Label(message, systemImage: "exclamationmark.triangle")
                .font(.title3.weight(.semibold))
            if !stderrTail.isEmpty {
                ScrollView {
                    Text(stderrTail.joined(separator: "\n"))
                        .font(.caption.monospaced())
                        .textSelection(.enabled)
                        .frame(maxWidth: .infinity, alignment: .leading)
                }
                .frame(maxHeight: 200)
            }
            RepoPathField(state: state)
            Button("Try Again") { Task { await state.restart() } }
                .keyboardShortcut(.defaultAction)
        }
        .padding(32)
        .frame(maxWidth: 640)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
    }
}

struct RepoPathField: View {
    @Bindable var state: AppState

    var body: some View {
        LabeledContent("Repo path") {
            TextField("Repo path", text: $state.repoPath, prompt: Text("~/code/tune-sort"))
                .textFieldStyle(.roundedBorder)
                .labelsHidden()
        }
    }
}
