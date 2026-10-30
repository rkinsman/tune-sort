import SwiftUI
import TuneSortCore

/// The main window: sidebar, song table and the selected song's panel.
struct AppView: View {
    let session: Session
    let restart: () -> Void

    @State private var confirmingSort = false
    @State private var confirmation = ""

    private var app: AppModel { session.app }

    private var isRunning: Bool { app.runState != .idle }

    var body: some View {
        NavigationSplitView {
            SidebarView(app: app)
                .navigationSplitViewColumnWidth(min: 180, ideal: 220)
        } content: {
            SongTableView(app: app)
                .navigationSplitViewColumnWidth(min: 380, ideal: 560)
        } detail: {
            SidePanelView(app: app, panel: session.panel)
                .navigationSplitViewColumnWidth(min: 260, ideal: 300)
        }
        .navigationTitle(title)
        .safeAreaInset(edge: .top, spacing: 0) {
            if let banner = app.banner {
                BannerView(banner: banner, restart: restart, dismiss: { app.banner = nil })
            }
        }
        .toolbar { toolbar }
        .confirmationDialog(confirmation, isPresented: $confirmingSort) {
            Button("Sort") { Task { await app.sort() } }
            Button("Cancel", role: .cancel) {}
        } message: {
            Text("This changes your Music library.")
        }
    }

    private var title: String {
        switch app.selection {
        case .needsReview?: "Needs review"
        case .allSongs?: "All songs"
        case .playlist(let name)?, .tuningPlaylist(let name)?: name
        case nil: "TuneSort"
        }
    }

    @ToolbarContentBuilder
    private var toolbar: some ToolbarContent {
        ToolbarItem(placement: .navigation) {
            Picker("Instrument", selection: instrumentBinding) {
                ForEach(Instrument.allCases, id: \.self) { i in
                    Text(i.rawValue.capitalized).tag(i)
                }
            }
            .pickerStyle(.segmented)
            .labelsHidden()
            .disabled(isRunning)
        }
        ToolbarItem(placement: .primaryAction) {
            SourcesMenu(app: app, settings: session.settings)
                .disabled(isRunning)
        }
        ToolbarItemGroup(placement: .primaryAction) {
            if case let .running(done, total, _) = app.runState {
                HStack(spacing: 8) {
                    Text("Sorting \(done) / \(total)")
                        .monospacedDigit()
                    ProgressView(value: Double(done), total: Double(max(total, 1)))
                        .frame(width: 120)
                }
                Button("Stop") { Task { await app.stop() } }
            } else {
                Button("Preview") { Task { await app.preview() } }
                    .disabled(!app.canRun)
                    .help("Dry run: show where each song would go, without changing Music")
                Button("Sort") {
                    confirmation = app.sortConfirmation()
                    confirmingSort = true
                }
                .disabled(!app.canRun)
            }
        }
    }

    private var instrumentBinding: Binding<Instrument> {
        Binding(
            get: { app.instrument },
            set: { i in
                guard i != app.instrument else { return }
                app.sourcesOverride = nil
                Task { await app.setInstrument(i) }
            })
    }
}

/// The per-run source order: the saved order, or another order or a single source.
struct SourcesMenu: View {
    let app: AppModel
    let settings: SettingsModel

    private var choices: [SourceChoice] {
        sourceChoices(enabled: (settings.orders[app.instrument] ?? []).filter(\.enabled).map(\.name))
    }

    var body: some View {
        Menu {
            ForEach(choices, id: \.self) { choice in
                Button {
                    app.sourcesOverride = choice.order
                } label: {
                    checked(app.sourcesOverride == choice.order, choice.label)
                }
                if choice.order == nil && choices.count > 1 { Divider() }
            }
        } label: {
            Label(label, systemImage: "list.number")
                .labelStyle(.titleAndIcon)
        }
        .help("Source order for the next run")
    }

    private var label: String {
        guard let o = app.sourcesOverride else { return "Sources" }
        return "Sources: " + o.joined(separator: ", ")
    }

    @ViewBuilder
    private func checked(_ on: Bool, _ text: String) -> some View {
        if on { Label(text, systemImage: "checkmark") } else { Text(text) }
    }
}
