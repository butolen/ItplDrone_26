namespace ITPDroneGUI.Components;

public sealed class SortableListMoveEventArgs
{
    public string ItemId { get; init; } = "";
    public int OldIndex { get; init; }
    public int NewIndex { get; init; }
}

public sealed class SortableListExternalDropEventArgs
{
    public string Payload { get; init; } = "";
    public int NewIndex { get; init; }
}
