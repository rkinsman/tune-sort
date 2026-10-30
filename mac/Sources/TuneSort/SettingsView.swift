import SwiftUI
import TuneSortCore

/// The Settings window (⌘,): source order per instrument, the repo path and the helper log.
struct SettingsView: View {
    let state: AppState

    var body: some View {
        TabView {
            Group {
                if let session = state.session {
                    SourcesSettings(settings: session.settings)
                } else {
                    ContentUnavailableView(
                        "The helper isn't running", systemImage: "bolt.horizontal.circle",
                        description: Text("Source order can be changed once the helper starts."))
                }
            }
            .tabItem { Label("Sources", systemImage: "list.number") }
            GeneralSettings(state: state)
                .tabItem { Label("Helper", systemImage: "gearshape") }
            HelperLog(transport: state.session?.transport)
                .tabItem { Label("Log", systemImage: "text.alignleft") }
        }
        .frame(width: 520, height: 460)
    }
}

struct SourcesSettings: View {
    let settings: SettingsModel

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Sources are tried in this order; drag to reorder. At least one stays on.")
                .foregroundStyle(.secondary)
            if let error = settings.error {
                Label(error, systemImage: "exclamationmark.triangle.fill")
                    .foregroundStyle(.red)
                    .textSelection(.enabled)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(alignment: .top, spacing: 16) {
                ForEach(Instrument.allCases, id: \.self) { i in
                    InstrumentOrder(settings: settings, instrument: i)
                }
            }
        }
        .padding()
        .task { await settings.load() }
    }
}

struct InstrumentOrder: View {
    let settings: SettingsModel
    let instrument: Instrument

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(instrument.rawValue.capitalized).font(.headline)
            List {
                ForEach(settings.orders[instrument] ?? [], id: \.name) { source in
                    Toggle(source.name, isOn: Binding(
                        get: { source.enabled },
                        set: { _ in Task { await settings.toggle(instrument, source.name) } }))
                }
                .onMove { from, to in
                    Task { await settings.move(instrument, from: from, to: to) }
                }
            }
            .listStyle(.bordered)
            .frame(minHeight: 140)
            Button("Reset to Default") { Task { await settings.reset(instrument) } }
        }
    }
}

struct GeneralSettings: View {
    @Bindable var state: AppState

    var body: some View {
        Form {
            Section {
                if let session = state.session {
                    RepoPathSetting(settings: session.settings)
                } else {
                    RepoPathField(state: state)
                }
                Text("The app runs the helper at <repo>/.venv/bin/tune-sort. Run `uv sync` in the repo to install it.")
                    .font(.caption)
                    .foregroundStyle(.secondary)
                Button("Restart Helper") { Task { await state.restart() } }
            }
        }
        .formStyle(.grouped)
    }
}

struct RepoPathSetting: View {
    @Bindable var settings: SettingsModel

    var body: some View {
        TextField("Repo path", text: $settings.repoPath)
    }
}

/// The helper's stderr (its last 50 lines), refreshed every second.
struct HelperLog: View {
    let transport: ProcessTransport?

    var body: some View {
        TimelineView(.periodic(from: .now, by: 1)) { _ in
            let lines = transport?.stderrTail ?? []
            ScrollView {
                Text(lines.isEmpty ? "No helper output." : lines.joined(separator: "\n"))
                    .font(.caption.monospaced())
                    .foregroundStyle(lines.isEmpty ? .secondary : .primary)
                    .textSelection(.enabled)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(8)
            }
            .defaultScrollAnchor(.bottom)
        }
        .padding()
    }
}
