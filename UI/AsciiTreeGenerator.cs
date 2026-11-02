using TheSimpsonsGame.FileViewer.UI.Models;

namespace TheSimpsonsGame.FileViewer.UI;

public static class AsciiTreeGenerator
{
    public static List<AsciiTreeRow> GenerateRows(IEnumerable<FileTreeItem> rootNodes, string filter = "")
    {
        var rows = new List<AsciiTreeRow>();
        bool isFiltered = !string.IsNullOrWhiteSpace(filter);
        string filterLower = filter.Trim().ToLowerInvariant();

        void EmitArchiveChildren(FileTreeItem parentNode, string prefix)
        {
            var children = parentNode.Children;
            for (int idx = 0; idx < children.Count; idx++)
            {
                var child = children[idx];
                bool isLast = idx == children.Count - 1;
                bool hasGrandchildren = child.Children.Count > 0;
                string tag = child.ColorTag;
                string label = child.Name;

                if (isFiltered && !MatchesFilter(child, filterLower))
                {
                    continue;
                }

                if (hasGrandchildren)
                {
                    string conn = $"{prefix}{(isLast ? "\\---" : "+---")}";
                    rows.Add(new AsciiTreeRow { Prefix = conn, Label = label, ColorTag = tag, Node = child });
                    if (child.IsOpen || isFiltered)
                    {
                        string childPrefix = $"{prefix}{(isLast ? "    " : "|   ")}";
                        EmitArchiveChildren(child, childPrefix);
                    }
                }
                else
                {
                    rows.Add(new AsciiTreeRow { Prefix = $"{prefix}    ", Label = label, ColorTag = tag, Node = child });
                }
            }
        }

        void EmitDirectoryChildren(FileTreeItem dirNode, string prefix)
        {
            var children = dirNode.Children;
            var fileChildren = children.Where(c => c.IsFile).OrderBy(c => c.Name, StringComparer.OrdinalIgnoreCase).ToList();
            var dirChildren = children.Where(c => c.IsDirectory).OrderBy(c => c.Name, StringComparer.OrdinalIgnoreCase).ToList();
            var otherChildren = children.Where(c => !c.IsFile && !c.IsDirectory).ToList();

            if (isFiltered)
            {
                fileChildren = fileChildren.Where(f => MatchesFilter(f, filterLower)).ToList();
                dirChildren = dirChildren.Where(d => MatchesFilter(d, filterLower)).ToList();
            }

            bool hasDirs = dirChildren.Count > 0;
            string fileConn = hasDirs ? $"{prefix}|   " : $"{prefix}    ";

            foreach (var fnode in fileChildren)
            {
                rows.Add(new AsciiTreeRow { Prefix = fileConn, Label = fnode.Name, ColorTag = fnode.ColorTag, Node = fnode });
                if (fnode.IsOpen || (isFiltered && fnode.IsArchive))
                {
                    EmitArchiveChildren(fnode, fileConn);
                }
            }

            if (fileChildren.Count == 0 && dirChildren.Count == 0 && otherChildren.Count > 0)
            {
                foreach (var onode in otherChildren)
                {
                    rows.Add(new AsciiTreeRow { Prefix = $"{prefix}    ", Label = onode.Name, ColorTag = "unknown", Node = dirNode });
                }
            }

            if (fileChildren.Count > 0 && dirChildren.Count > 0)
            {
                rows.Add(new AsciiTreeRow { Prefix = $"{prefix}|", Label = "", ColorTag = "tree_default", Node = null });
            }

            for (int idx = 0; idx < dirChildren.Count; idx++)
            {
                var dnode = dirChildren[idx];
                bool isLast = idx == dirChildren.Count - 1;
                string conn = $"{prefix}{(isLast ? "\\---" : "+---")}";
                rows.Add(new AsciiTreeRow { Prefix = conn, Label = dnode.Name, ColorTag = "tree_default", Node = dnode });

                bool isDirOpen = dnode.IsOpen || (isFiltered && !dnode.IsDeferred);
                if (isDirOpen)
                {
                    string childPrefix = $"{prefix}{(isLast ? "    " : "|   ")}";
                    EmitDirectoryChildren(dnode, childPrefix);
                    if (!isLast)
                    {
                        rows.Add(new AsciiTreeRow { Prefix = $"{prefix}|", Label = "", ColorTag = "tree_default", Node = null });
                    }
                }
            }
        }

        foreach (var rootNode in rootNodes)
        {
            if (rootNode.IsDirectory)
            {
                rows.Add(new AsciiTreeRow { Prefix = "", Label = rootNode.Name, ColorTag = "tree_default", Node = rootNode });
                if (rootNode.IsOpen || isFiltered)
                {
                    EmitDirectoryChildren(rootNode, "");
                }
            }
            else
            {
                rows.Add(new AsciiTreeRow { Prefix = "", Label = rootNode.Name, ColorTag = rootNode.ColorTag, Node = rootNode });
                if (rootNode.IsOpen || (isFiltered && rootNode.IsArchive))
                {
                    EmitArchiveChildren(rootNode, "    ");
                }
            }
        }

        return rows;
    }

    private static bool MatchesFilter(FileTreeItem node, string filter)
    {
        if (string.IsNullOrEmpty(filter)) return true;
        if (node.Name.Contains(filter, StringComparison.OrdinalIgnoreCase)) return true;
        if (node.FullPath.Contains(filter, StringComparison.OrdinalIgnoreCase)) return true;

        foreach (var child in node.Children)
        {
            if (MatchesFilter(child, filter)) return true;
        }

        return false;
    }
}

