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
            HkXmlTagfileWriterV3.Instance.Write(dest + ".xml", obj);

            Console.WriteLine("Write bin to " + dest);
            HkBinaryTagfileWriter.Write(dest + ".out", obj, HkSdkVersion.V20160200);
        }

        private static void DMain(string[] args) {
            var skeleton =
                @"D:\Steam\steamapps\common\ELDEN RING\Game\dsanime\c2120-anibnd\GR\data\INTERROOT_win64\chr\c2120\hkx\skeleton.hkx";
            // var compendium =
            //     @"D:\Steam\steamapps\common\ELDEN RING\Game\dsanime\c2120-anibnd\GR\data\INTERROOT_win64\chr\c2120\hkx\c7400.compendium";
            var compendium = "";

            // var skeleton =
            //     @"D:\Steam\steamapps\common\ELDEN RING\Game\chr\c2120-anibnd\GR\data\INTERROOT_win64\chr\c2120\hkx\skeleton.hkx";
            // var compendium =
            //     @"D:\Steam\steamapps\common\ELDEN RING\Game\chr\c2120_div00-anibnd\GR\data\INTERROOT_win64\chr\c2120\hkx_div00_compendium\c2120_div00.compendium";
            Read(skeleton, compendium, @"D:\Steam\steamapps\common\ELDEN RING\Game\dsanime\c2120-anibnd\GR\data\INTERROOT_win64\chr\c2120\hkx\" + Path.GetFileName(skeleton));
            // Read(skeleton);
        }

        private static void Main(string[] args) {
            if (args.Length <= 0) {
                throw new ArgumentException("Must have at least 1 arg");
            }

            string path = args[0], compendium = "", dest = args[0];
            if (args.Length >= 2) {
                compendium = args[1];
                if (string.IsNullOrWhiteSpace(compendium)) {
                    compendium = "";
                }
            }

            if (args.Length >= 3) {
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