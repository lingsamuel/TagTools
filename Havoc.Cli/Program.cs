using System;
using System.IO;
using Havoc.IO.Tagfile.Binary;
using Havoc.IO.Tagfile.Xml;
using Havoc.IO.Tagfile.Xml.V3;

namespace Havoc.Cli {
    internal class Program {
        private static void Read(string path, string compendium = "", string dest = "") {
            var obj = HkBinaryTagfileReader.Read(path, compendium);
            Console.WriteLine("Write xml to " + dest);
            HkXmlTagfileWriterV3.Instance.Write(dest + ".2016.xml", obj);

            Console.WriteLine("Write bin to " + dest);
            HkBinaryTagfileWriter.Write(dest + ".2016.hkx", obj, HkSdkVersion.V20160200);
        }

        private static void RMain(string[] args) {
            Debug.DebugLevel = Debug.DebugInfoType.ReadProcess |
                               // Debug.DebugInfoType.WriteProcess |
                               // Debug.DebugInfoType.TypeDef |
                               Debug.DebugInfoType.Temporary;

            var skeleton =
                @"D:\Steam\steamapps\common\ELDEN RING\Game\chr\c0000-behbnd\GR\data\INTERROOT_win64\action\c0000\Export\Behaviors\c0000.hkx";
            var compendium = @"";

            Read(skeleton, compendium,
                @"D:\Steam\steamapps\common\ELDEN RING\Game\dsanime\output\" + Path.GetFileName(skeleton) + ".beh");
            // Read(skeleton);
        }

        private static void Main(string[] args) {
            if (args.Length <= 0) {
                Console.WriteLine(@"Havoc CLI v0.2.0 -- Read HKX V2018 and convert to V2016
Usage:
  Havoc.Cli.exe input             -- read from input path, write in-place 
  Havoc.Cli.exe input output      -- read from input path, write to output path 
  Havoc.Cli.exe input type output -- read from input path, take type compendium from type path, write to output path 
");
                return;
                // throw new ArgumentException("Must have at least 1 arg");
            }

            string path = args[0], compendium = "", dest = args[0];
            if (args.Length == 2) {
                dest = args[1];
            } else if (args.Length >= 3) {
                compendium = args[1];
                dest = args[2];
            }

            // Console.WriteLine($"Path: {path}, Compendium: {compendium}, Dest: {dest}");

            var obj = HkBinaryTagfileReader.Read(path, compendium);
            HkBinaryTagfileWriter.Write(dest, obj, HkSdkVersion.V20160200);
            HkXmlTagfileWriterV3.Instance.Write(dest + ".xml", obj);
            // HkXmlTagfileWriterV3.Instance.Write(dest + ".2012.xml", obj);
        }
    }
}