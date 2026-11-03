using System.Buffers.Binary;

namespace TheSimpsonsGame.FileViewer.Formats;

public class MibBusEntry
{
    public int Index { get; set; }
    public uint BusHash { get; set; }
    public float VolumeOrDucking { get; set; }
    public float AttackSec { get; set; }
    public float ReleaseSec { get; set; }
    public float Threshold { get; set; }
    public float PitchOffset { get; set; }
    public float FilterCutoff { get; set; }
    public float WetDryMix { get; set; }
    public float ReverbSend { get; set; }
    public uint Flags { get; set; }
}

public class MibDspOverrideEntry
{
    public int Index { get; set; }
    public uint BusHash { get; set; }
    public uint EffectNodeId { get; set; }
    public uint ParameterId { get; set; }
    public float Value { get; set; }
    public float TargetValue { get; set; }
    public uint Flags { get; set; }
    public uint TransitionCurve { get; set; }
}

public class MibData
{
    public uint MixCategoryId { get; set; }
    public uint BusCount { get; set; }
    public uint DspOverrideCount { get; set; }
    public uint PayloadSize { get; set; }
    public List<MibBusEntry> Buses { get; } = new();
    public List<MibDspOverrideEntry> DspOverrides { get; } = new();
}

public static class MibParser
{
    public static MibData? Parse(byte[] data)
    {
        if (data.Length < 48) return null;

        ReadOnlySpan<byte> span = data;
        uint mixCat = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x18, 4));
        uint busCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x20, 4));
        uint dspCount = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x28, 4));
        uint payloadSize = BinaryPrimitives.ReadUInt32BigEndian(span.Slice(0x2C, 4));

        long expectedSize = 48 + (long)busCount * 44 + (long)dspCount * 32;
        if (expectedSize != data.Length) return null;

        var mib = new MibData
        {
            MixCategoryId = mixCat,
            BusCount = busCount,
            DspOverrideCount = dspCount,
            PayloadSize = payloadSize
        };

        for (int i = 0; i < (int)busCount; i++)
        {
            int pos = 48 + i * 44;
            var rec = span.Slice(pos, 44);
            mib.Buses.Add(new MibBusEntry
            {
                Index = i,
                BusHash = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(0, 4)),
                VolumeOrDucking = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(4, 4)),
                AttackSec = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(8, 4)),
                ReleaseSec = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(12, 4)),
                Threshold = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(16, 4)),
                PitchOffset = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(20, 4)),
                FilterCutoff = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(24, 4)),
                WetDryMix = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(28, 4)),
                ReverbSend = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(32, 4)),
                Flags = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(36, 4))
            });
        }

        int dspStart = 48 + (int)busCount * 44;
        for (int i = 0; i < (int)dspCount; i++)
        {
            int pos = dspStart + i * 32;
            var rec = span.Slice(pos, 32);
            mib.DspOverrides.Add(new MibDspOverrideEntry
            {
                Index = i,
                BusHash = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(0, 4)),
                EffectNodeId = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(8, 4)),
                ParameterId = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(12, 4)),
                Flags = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(16, 4)),
                Value = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(20, 4)),
                TargetValue = BinaryPrimitives.ReadSingleBigEndian(rec.Slice(24, 4)),
                TransitionCurve = BinaryPrimitives.ReadUInt32BigEndian(rec.Slice(28, 4))
            });
        }

        return mib;
    }

    public static TableDataModel ToTable(MibData mib)
    {
        var model = new TableDataModel
        {
            Headers = new List<string> { "Index", "Type", "Bus / Target Hash", "Volume / Value", "Attack / Release", "Filter / Node" },
            Summary = $"MIB: {mib.Buses.Count} mix buses, {mib.DspOverrides.Count} DSP overrides, Category 0x{mib.MixCategoryId:X}"
        };

        foreach (var b in mib.Buses)
        {
            model.Rows.Add(new List<string>
            {
                b.Index.ToString(),
                "Mix Bus",
                $"0x{b.BusHash:08X}",
                $"Vol: {b.VolumeOrDucking:F2}",
                $"{b.AttackSec:F2}s / {b.ReleaseSec:F2}s",
                $"Cutoff: {b.FilterCutoff:F1}, Send: {b.ReverbSend:F2}"
            });
        }

        foreach (var d in mib.DspOverrides)
        {
            model.Rows.Add(new List<string>
            {
                d.Index.ToString(),
                "DSP Override",
                $"Bus 0x{d.BusHash:08X}",
                $"Value: {d.Value:F2} (Target {d.TargetValue:F2})",
                $"Param: 0x{d.ParameterId:08X}",
                $"Node: 0x{d.EffectNodeId:08X}"
            });
        }

        return model;
    }

    public static TreeNodeModel ToTreeNode(MibData mib)
    {
        var root = new TreeNodeModel($"MIB Audio Mix Snapshot ({mib.Buses.Count} buses, {mib.DspOverrides.Count} DSP overrides, Category 0x{mib.MixCategoryId:X})");

        var children = new List<TreeNodeModel>
        {
            new($"Header: Category 0x{mib.MixCategoryId:X}, Mix Buses: {mib.Buses.Count}, DSP Overrides: {mib.DspOverrides.Count}, Payload: 0x{mib.PayloadSize:X} bytes")
        };

        if (mib.Buses.Count > 0)
        {
            var busNodes = new List<TreeNodeModel>();
            foreach (var b in mib.Buses)
            {
                busNodes.Add(new TreeNodeModel(
                    $"[{b.Index}] Bus 0x{b.BusHash:08X}: Vol {b.VolumeOrDucking:F2}, Att/Rel: {b.AttackSec:F2}s/{b.ReleaseSec:F2}s, Send: {b.ReverbSend:F2}"));
            }
            children.Add(new TreeNodeModel($"Mix Buses ({mib.Buses.Count} channels)", busNodes));
        }

        if (mib.DspOverrides.Count > 0)
        {
            var dspNodes = new List<TreeNodeModel>();
            foreach (var d in mib.DspOverrides)
            {
                dspNodes.Add(new TreeNodeModel(
                    $"[{d.Index}] Bus 0x{d.BusHash:08X} Node 0x{d.EffectNodeId:08X}: Value {d.Value:F2} (Param 0x{d.ParameterId:08X})"));
            }
            children.Add(new TreeNodeModel($"DSP Overrides ({mib.DspOverrides.Count} nodes)", dspNodes));
        }

        root.Children = children;
        return root;
    }
}

