import SwiftUI
import TuneSortCore

/// Needs review, All songs, the instrument's playlists, then its tuning playlists (dimmed).
struct SidebarView: View {
    let app: AppModel

    private var selection: Binding<SidebarItem?> {
        Binding(
            get: { app.selection },
            set: { item in
                guard let item, item != app.selection else { return }
                Task { await app.select(item) }
            })
    }

    var body: some View {
        List(selection: selection) {
            Label("Needs review", systemImage: "questionmark.circle")
                .badge(app.reviewCount)
                .tag(SidebarItem.needsReview as SidebarItem?)
            Label("All songs", systemImage: "music.note.list")
                .tag(SidebarItem.allSongs as SidebarItem?)
            Section("Playlists") {
                ForEach(app.playlists, id: \.self) { name in
                    Label(name, systemImage: "music.note.list")
                        .tag(SidebarItem.playlist(name) as SidebarItem?)
                }
            }
            if !app.tuningPlaylists.isEmpty {
                Section("Tuning playlists") {
                    ForEach(app.tuningPlaylists, id: \.self) { name in
                        Label(name, systemImage: "tuningfork")
                            .foregroundStyle(.secondary)
                            .tag(SidebarItem.tuningPlaylist(name) as SidebarItem?)
                    }
                }
            }
        }
        .listStyle(.sidebar)
        .disabled(app.runState != .idle)
    }
}
