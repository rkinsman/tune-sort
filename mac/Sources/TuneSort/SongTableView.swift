import SwiftUI
import TuneSortCore

/// The selection's songs: Song, Tuning and Source, with the last run's summary below.
struct SongTableView: View {
    @Bindable var app: AppModel
    /// The row under the pointer, highlighted like Music's song list.
    @State private var hover = RowHoverState()

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
                        .modifier(hover(row, paints: true))
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

    private func hover(_ row: SongRow, paints: Bool = false) -> RowHover {
        RowHover(
            state: hover, rowID: row.id, isSelected: app.selectedRowID == row.id, paints: paints)
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

/// Which song row the pointer is over. Every cell reads it, so each cell redraws itself
/// when it changes; Table doesn't reload a row whose data hasn't changed.
@Observable final class RowHoverState {
    var rowID: SongRow.ID?
}

/// Fills a table cell and tracks the pointer over it. Applied to every cell of a row, so
/// hovering anywhere on the row counts. Only the first column's cell (`paints`) draws the
/// highlight, as one band stretched across the whole row behind the other cells: one
/// translucent layer, so the gaps between columns get the same shade. SwiftUI's onHover
/// never fires inside Table cells, so the pointer is tracked with an AppKit tracking area.
struct RowHover: ViewModifier {
    let state: RowHoverState
    let rowID: SongRow.ID
    let isSelected: Bool
    let paints: Bool

    func body(content: Content) -> some View {
        let isHovered = paints && state.rowID == rowID && !isSelected
        return content
            .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .leading)
            .background(alignment: .leading) {
                if isHovered {
                    // Wider than any window, so it runs under every column; the table's
                    // scroll view clips it at the row's edges.
                    Rectangle()
                        .fill(Color.primary.opacity(0.07))
                        .frame(width: 10_000)
                        .padding(.leading, -6)
                        .padding(.vertical, -4)
                }
            }
            .background(PointerTracker { inside in
                if inside {
                    state.rowID = rowID
                } else if state.rowID == rowID {
                    state.rowID = nil
                }
            })
    }
}

/// An invisible AppKit view that reports the pointer entering and leaving it. It never
/// takes clicks: hitTest returns nil, so selection works as before.
struct PointerTracker: NSViewRepresentable {
    let onChange: (Bool) -> Void

    func makeNSView(context: Context) -> TrackingView {
        let view = TrackingView()
        view.onChange = onChange
        return view
    }

    func updateNSView(_ view: TrackingView, context: Context) {
        view.onChange = onChange
    }

    final class TrackingView: NSView {
        var onChange: ((Bool) -> Void)?

        override func updateTrackingAreas() {
            super.updateTrackingAreas()
            for area in trackingAreas { removeTrackingArea(area) }
            addTrackingArea(NSTrackingArea(
                rect: .zero,
                options: [.mouseEnteredAndExited, .activeAlways, .inVisibleRect],
                owner: self))
        }

        override func mouseEntered(with event: NSEvent) { onChange?(true) }
        override func mouseExited(with event: NSEvent) { onChange?(false) }
        override func hitTest(_ point: NSPoint) -> NSView? { nil }
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
