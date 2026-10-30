import SwiftUI
import TuneSortCore

/// The selection's songs: Song, Tuning and Source, with the last run's summary below.
struct SongTableView: View {
    @Bindable var app: AppModel
    /// The row under the pointer, highlighted like Music's song list.
    @State private var hoveredRowID: SongRow.ID?

    var body: some View {
        if app.selection == nil {
            ContentUnavailableView(
                "Choose a playlist", systemImage: "music.note.list",
                description: Text("Pick a playlist in the sidebar to see its songs' tunings."))
        } else {
            VStack(spacing: 0) {
                if app.selection == .allSongs {
                    searchField
                }
                Table(app.rows, selection: $app.selectedRowID) {
                    TableColumn("Song") { row in
                        VStack(alignment: .leading, spacing: 1) {
                            Text(row.title)
                            Text(row.artist).font(.caption).foregroundStyle(.secondary)
                        }
                        .modifier(hover(row))
                    }
                    TableColumn("Tuning") { row in
                        TuningCell(status: row.status).modifier(hover(row))
                    }
                    .width(min: 120, ideal: 160)
                    TableColumn("Source") { row in
                        SourceCell(status: row.status).modifier(hover(row))
                    }
                    .width(min: 80, ideal: 110)
                }
                Divider()
                footer
            }
        }
    }

    private func hover(_ row: SongRow) -> RowHover {
        RowHover(
            isHovered: hoveredRowID == row.id && app.selectedRowID != row.id,
            onHover: { inside in
                if inside {
                    hoveredRowID = row.id
                } else if hoveredRowID == row.id {
                    hoveredRowID = nil
                }
            })
    }

    private var searchField: some View {
        HStack {
            Image(systemName: "magnifyingglass").foregroundStyle(.secondary)
            TextField("Search artist or title", text: $app.searchText)
                .textFieldStyle(.plain)
            if !app.searchText.isEmpty {
                Button { app.searchText = "" } label: { Image(systemName: "xmark.circle.fill") }
                    .buttonStyle(.borderless)
                    .foregroundStyle(.secondary)
            }
        }
        .padding(8)
        .background(.quaternary.opacity(0.5))
    }

    private var footer: some View {
        HStack {
            Text(app.lastSummary ?? "")
                .textSelection(.enabled)
            Spacer()
            Text(app.rows.count == 1 ? "1 song" : "\(app.rows.count) songs")
                .foregroundStyle(.secondary)
                .monospacedDigit()
        }
        .fixedSize(horizontal: false, vertical: true)
        .font(.callout)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
    }
}

/// Fills a table cell, tracks the pointer over it and paints the hover highlight. Applied
/// to every cell of a row, so the whole row lights up; the negative padding covers the
/// gaps between columns. Table has no row-hover API of its own.
struct RowHover: ViewModifier {
    let isHovered: Bool
    let onHover: (Bool) -> Void

    func body(content: Content) -> some View {
        content
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
            .contentShape(Rectangle())
            .onHover(perform: onHover)
            .background(
                Rectangle()
                    .fill(isHovered ? Color.primary.opacity(0.07) : .clear)
                    .padding(.horizontal, -6)
                    .padding(.vertical, -4))
    }
}

struct TuningCell: View {
    let status: RowStatus

    var body: some View {
        switch status {
        case .cached(let tuning, _, _):
            Text(tuning.name)
        case .review:
            Label("needs review", systemImage: "questionmark.circle")
                .foregroundStyle(.orange)
        case .unknown:
            Text("not looked up").foregroundStyle(.secondary)
        case .lookingUp:
            HStack(spacing: 6) {
                ProgressView().controlSize(.small)
                Text("looking up…").foregroundStyle(.secondary)
            }
        case .failed:
            Text("failed, will retry").foregroundStyle(.secondary)
        case .addError:
            Label("couldn't add", systemImage: "exclamationmark.triangle")
                .foregroundStyle(.red)
        }
    }
}

struct SourceCell: View {
    let status: RowStatus

    var body: some View {
        if case let .cached(_, source, confirmed) = status {
            HStack(spacing: 4) {
                Text(source)
                if confirmed {
                    Image(systemName: "checkmark.seal").foregroundStyle(.secondary).help("Confirmed")
                }
            }
        } else {
            Text("")
        }
    }
}
