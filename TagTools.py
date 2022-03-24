import struct
import sys
import os

import xml.etree.cElementTree as ET

import subprocess


def debug(*args):
    if False:
        print(" ".join(map(str, args)))


class TagSubType(object):
    Void = 0x0
    Invalid = 0x1
    Bool = 0x2
    String = 0x3
    Int = 0x4
    Float = 0x5
    Pointer = 0x6
    Class = 0x7
    Array = 0x8
    Tuple = 0x28
    TypeMask = 0xff
    IsSigned = 0x200
    Float32 = 0x1746
    Int8 = 0x2000
    Int16 = 0x4000
    Int32 = 0x8000
    Int64 = 0x10000

class TagFlag(object):
    SubType = 0x1
    Pointer = 0x2
    Version = 0x4
    ByteSize = 0x8
    AbstractValue = 0x10
    Members = 0x20
    Interfaces = 0x40
    Unknown = 0x80


class TagFlagV2(object):
    HasFormatInfo = 0x1
    HasSubType = 0x2
    Version = 0x4
    ByteSize = 0x8
    HasUnknownFlags = 0x10
    Members = 0x20
    Interfaces = 0x40
    Unknown = 0x80


class TagMember(object):
    def __init__(self):
        self.name = ""
        self.flags = 0
        self.byteOffset = 0
        self.typ = None
        self.tag = None


class TagTemplate(object):
    def __init__(self, name="v", value=0):
        self.name = name
        self.value = value

    @property
    def isInt(self):
        return self.name[0] == "v"

    @property
    def isType(self):
        return self.name[0] == "t"


class TagType(object):
    def __init__(self, name=""):
        self.name = name
        self.templates = []
        self.parent = None
        self.flags = 1
        self.mFormatInfo = 0
        self.mSubType = None
        self.version = 0
        self.byteSize = 0
        self.alignment = 0
        self.abstractValue = 0
        self.members = []
        self.interfaces = []
        self.hsh = 0
        self.tag = None

    @property
    def superType(self):
        if not self.flags & TagFlag.SubType:
            if self.parent == None:
                return None
            return self.parent.superType

        else:
            return self
        # if self.flags & TagFlagV2.HasFormatInfo != 0:
        #     return self
        # if self.parent is not None:
        #     return self.parent.superType
        # return self

    @property
    def subType(self):
        # return self.mFormatInfo & TagSubType.TypeMask # 0xF  #
        return self.mFormatInfo & 0x7F  #

    @property
    def allMembers(self):
        if self.parent:
            for member in self.parent.allMembers:
                yield member

        for member in self.members:
            yield member

    @property
    def tupleSize(self):
        return self.mFormatInfo >> 8


class TagObject(object):
    def __init__(self, value, typ):
        self.value = value
        self.typ = typ
        self.attachment = None


class TagItem(object):
    def __init__(self):
        self.typ = None
        self.offset = 0
        self.count = 0
        self.isPtr = False
        self.value = None


class TagSectionReader(object):
    def __init__(self, r, *signatures):
        self.r = r
        self.offset = r.f.tell() + 8
        self.size = (r.readFormat(">I") & 0x3FFFFFFF) - 8
        self.signature = r.f.read(4)
        debug(self.signature, self.size)

        if not self.signature in signatures:
            raise ValueError("Invalid signature, expected {}, got {}".format(", ".join(signatures), self.signature))

    @property
    def end(self):
        return self.r.f.tell() >= (self.offset + self.size)

    def __enter__(self):
        self.r.f.seek(self.offset)
        return self

    def __exit__(self, arg1, arg2, arg3):
        self.r.f.seek(self.offset + self.size)


class TagFileType(object):
    Invalid = -1
    Object = 0
    Compendium = 1


class TagReader(object):
    def __init__(self, f, compendium=None):
        self.f = f
        self.dataOffset = 0
        self.types = []
        self.items = []
        self.ids = []
        self.compendium = compendium
        self.readRootSection()

    def __enter__(self):
        return self

    def __exit__(self, arg1, arg2, arg3):
        if (self.compendium != None):
            self.compendium.f.close()

        self.f.close()

    @staticmethod
    def fromFile(inputFileName, compendiumFileName=None):
        compendium = None
        if (compendiumFileName != None and os.path.exists(compendiumFileName)):
            debug("read compendium file")
            compendium = TagReader(open(compendiumFileName, "rb"))
            debug("read compendium file finished")

        debug("read input file")
        with TagReader(open(inputFileName, "rb"), compendium) as r:
            debug("read input file finished, items count:", len(r.items))
            return r.getObject(0)

    @staticmethod
    def checkFile(inputFileName):
        with open(inputFileName, "rb") as f:
            f.seek(4)

            signature = f.read(4)
            if (signature == "TAG0"):
                return TagFileType.Object
            elif (signature == "TCM0"):
                return TagFileType.Compendium
            else:
                return TagFileType.Invalid

    def readTypeSection(self):
        with TagSectionReader(self, "TYPE", "TCRF") as t1:
            debug("=============== " + t1.signature)
            if (t1.signature == "TCRF"):
                compendiumId = self.f.read(8)

                if (self.compendium == None):
                    raise ValueError("Missing compendium, tag file cannot be parsed")

                if (compendiumId not in self.compendium.ids):
                    raise ValueError("Compendium ID could not be found")

                self.types = self.compendium.types
                return

            with TagSectionReader(self, "TPTR") as t2:
                pass

            with TagSectionReader(self, "TSTR") as t3:
                typeStrings = self.f.read(t3.size).split("\0")

            with TagSectionReader(self, "TNAM", "TNA1") as t4:
                debug("=============== " + t4.signature)
                typeCount = self.readPacked()
                debug("type count", typeCount)
                self.types = [TagType() for x in xrange(typeCount + 1)]
                self.types[0] = None

                for typ in self.types[1:]:
                    typ.name = typeStrings[self.readPacked()]

                    for i in xrange(self.readPacked()):
                        template = TagTemplate(typeStrings[self.readPacked()], self.readPacked())

                        if template.isType:
                            # print("template " + template.name + " has type " + self.types[template.value].name + " (" + str(template.value))
                            template.value = self.types[template.value]

                        typ.templates.append(template)
                debug("types", [x.name for x in self.types[1:]])

            with TagSectionReader(self, "FSTR") as t5:
                fieldStrings = self.f.read(t5.size).split("\0")
                debug("field strings:", fieldStrings, len(fieldStrings))

            startIdx = self.f.tell()
            # debug("TBDY_Index", startIdx)
            with TagSectionReader(self, "TBOD", "TBDY") as t6:
                startIdx = self.f.tell()
                # debug("TBDY_Index", startIdx)
                # debug("types len: ", len(self.types))
                debug("=============== " + t6.signature)
                while not t6.end:
                    typeIndex = self.readPacked()

                    if typeIndex == 0:
                        continue

                    typ = self.types[typeIndex]
                    typ.parent = self.types[self.readPacked()]
                    typ.flags = self.readPacked()

                    if typ.flags & TagFlagV2.HasFormatInfo:
                        typ.mFormatInfo = self.readPacked()

                    if typ.flags & TagFlagV2.HasSubType:
                        typ.mSubType = self.types[self.readPacked()]

                    if typ.flags & TagFlagV2.Version:
                        typ.version = self.readPacked()

                    if typ.flags & TagFlagV2.ByteSize:
                        typ.byteSize = self.readPacked()
                        typ.alignment = self.readPacked()

                    if typ.flags & TagFlagV2.HasUnknownFlags:
                        typ.abstractValue = self.readPacked()

                    if typ.flags & TagFlag.Members:
                        firstByteInMemberCount = self.readFormat("B")
                        if firstByteInMemberCount == 0xC3:
                            firstByteInMemberCount = self.readFormat("B")
                            if firstByteInMemberCount == 0:
                                firstByteInMemberCount = self.readPacked()
                        # startIdx = self.f.tell()
                        # debug("start idx", startIdx)
                        # memberCount = self.readPacked(firstByteInMemberCount)
                        memberCount = firstByteInMemberCount & 0x3F
                        # print("Type " + typ.name + " (" + str(memberCount) + ")")
                        # print("memberCount", memberCount)
                        for i in xrange(memberCount):
                            member = TagMember()
                            fieldIndex = self.readPacked()
                            # print("fieldIndex", fieldIndex)
                            member.name = fieldStrings[fieldIndex]
                            member.flags = self.readPacked()
                            member.byteOffset = self.readPacked()
                            typesIndex = self.readPacked()
                            # print("types idx", typesIndex)
                            member.typ = self.types[typesIndex]
                            # print("    " + member.name +": " + member.typ.name + ", Flags: (" + str(member.flags) + ") (offset " + str(member.byteOffset)+ ") (typeidx: " + str(typesIndex) + ")")
                            typ.members.append(member)
                    # else:
                    #     print("Type " + typ.name)

                    if typ.flags & TagFlag.Interfaces:
                        typ.interfaces = [
                        	(self.types[self.readPacked()], self.readPacked())
                        	for x in xrange(self.readPacked())]
                        # interfaceCount = self.readPacked()
                        # typ.interfaces = []
                        # for x in xrange(interfaceCount):
                        #     interfaceType = self.types[self.readPacked()]
                        #     interfaceFlag = self.readPacked()
                        #     typ.interfaces.append(
                        #         (interfaceType, interfaceFlag)
                        #     )

                    if typ.flags & TagFlag.Unknown:
                        raise ValueError("Flag 0x80 exists, handle it!")

            with TagSectionReader(self, "THSH") as t7:
                for i in xrange(self.readPacked()):
                    typeIndex = self.readPacked()
                    self.types[typeIndex].hsh = self.readFormat("<I")

            with TagSectionReader(self, "TPAD") as t8:
                pass

    def readIndexSection(self):
        with TagSectionReader(self, "INDX") as t1:
            with TagSectionReader(self, "ITEM") as t2:
                while not t2.end:
                    item = TagItem()
                    flag = self.readFormat("<I")
                    item.typ = self.types[flag & 0xFFFFFF]
                    item.isPtr = bool(flag & 0x10000000)
                    item.offset = self.dataOffset + self.readFormat("<I")
                    item.count = self.readFormat("<I")
                    self.items.append(item)

            with TagSectionReader(self, "PTCH") as t3:
                pass

    def readRootSection(self):
        with TagSectionReader(self, "TAG0", "TCM0") as t1:
            if (t1.signature == "TAG0"):
                debug("read tag0")
                with TagSectionReader(self, "SDKV") as t2:
                    version = self.f.read(8)
                    debug("read version " + version)
                    supportedVersion = ["20180100", "20160100", "20160200", "20150100"]
                    if (version not in supportedVersion):
                        raise ValueError("Invalid SDK version.")

                debug("reading DATA")
                with TagSectionReader(self, "DATA") as t3:
                    self.dataOffset = t3.offset

                debug("READING TAG0 Types")
                debug("READ TYPE")
                # oldTypes = self.types
                self.readTypeSection()
                # if (self.compendium is not None) and (len(self.types) > 0):
                #     self.types = oldTypes

                debug("reading INDX")
                self.readIndexSection()

            elif (t1.signature == "TCM0"):
                debug("read tcm0")
                with TagSectionReader(self, "TCID") as t4:
                    for i in xrange(t4.size / 8):
                        tcid = self.f.read(8)
                        self.ids.append(tcid)
                debug("READING TCM0 Types")
                self.readTypeSection()

    @staticmethod
    def getFormatString(flags, signed=False):
        ret = ""

        if flags & TagSubType.Int8:
            ret = "B"

        elif flags & TagSubType.Int16:
            ret = "<H"

        elif flags & TagSubType.Int32:
            ret = "<I"

        elif flags & TagSubType.Int64:
            ret = "<q"

        if flags & TagSubType.IsSigned or signed:
            return ret.lower()

        else:
            return ret

    def readObject(self, typ, offset=0, isTarget=False):
        # if not isTarget:
        #     isTarget = typ.name == "hkaDefaultAnimatedReferenceFrame"
        # if isTarget:
        #     print("ReadObj: " + typ.name + " Offset: " + str(offset))
        if offset == 0:
            offset = self.f.tell()

        else:
            self.f.seek(offset)

        typOrg = typ
        typ = typ.superType

        value = None

        if typ.subType == TagSubType.Bool:
            value = self.readFormat(TagReader.getFormatString(typ.mFormatInfo)) > 0

        elif typ.subType == TagSubType.String:
            value = "".join(map(chr, [x.value for x in self.readItemPtr()[:-1]]))

        elif typ.subType == TagSubType.Int:
            value = self.readFormat(TagReader.getFormatString(typ.mFormatInfo))

        elif typ.subType == TagSubType.Float:
            value = self.readFormat("<f")

        elif typ.subType == TagSubType.Pointer:
            value = self.readItemPtr()

            if len(value) == 1:
                value = value[0]

            else:
                value = None

        elif typ.subType == TagSubType.Class:
            # if isTarget:
            #     print("ReadObj: " + typ.name)
            #     print("ReadObj: " + str(typ.subType))
            value = {}
            for x in typ.allMembers:
                if isTarget:
                    print("    " + x.name + "    " + str(x.typ.name))
                value[x.name] = self.readObject(x.typ, offset + x.byteOffset)
            #
            # value = {x.name: self.readObject(x.typ, offset + x.byteOffset)
            #          for x in typ.allMembers}

        elif typ.subType == TagSubType.Array:
            value = self.readItemPtr()

        elif typ.subType == TagSubType.Tuple:
            value = tuple([self.readObject(typ.mSubType, offset + x * typ.mSubType.superType.byteSize)
                           for x in xrange(typ.tupleSize)])

        self.f.seek(offset + typ.byteSize)
        return TagObject(value, typOrg)

    def readItemPtr(self):
        index = self.readFormat("<I")

        if index == 0:
            return []

        else:
            debug("read item, len", len(self.items), "index", index)
            item = self.items[index]

            if item.value == None:
                item.value = [self.readObject(item.typ,
                                              item.offset + x * item.typ.superType.byteSize)
                              for x in xrange(item.count)]

            return item.value

    def readFormat(self, format):
        data = struct.unpack(format, self.f.read(struct.calcsize(format)))

        if len(data) == 1:
            return data[0]

        else:
            return data

    def readPacked(self, byte=None):
        debugMode = False
        if byte is None:
            byte = self.readFormat("B")
        else:
            debugMode = True
        if (byte & 0x80) == 0:
            return byte

        if debugMode:
            debug("further parse")
        case = byte >> 3
        if debugMode:
            debug("case", case)
        if (0x10 <= case) and (case <= 0x17):
            return (byte << 8 | self.readFormat("B")) & 0x3fff
        elif (0x18 <= case) and (case <= 0x1B):
            return (byte << 16 |
                    (self.readFormat("B") << 8) | self.readFormat("B")) & 0x1fffff
        elif (case == 0x1C):
            return (byte << 24 | (self.readFormat("B") << 16) |
                    (self.readFormat("B") << 8) | self.readFormat("B")) & 0x7ffffff
        elif (case == 0x1D):
            return (byte << 32 |
                    (self.readFormat("B") << 24) | (self.readFormat("B") << 16) |
                    (self.readFormat("B") << 8) | self.readFormat("B")) & 0x7FFFFFFFFFFFFFF
        elif (case == 0x1E):
            return (byte << 56 | (self.readFormat("B") << 48) |
                    (self.readFormat("B") << 40) | (self.readFormat("B") << 32) |
                    (self.readFormat("B") << 24) | (self.readFormat("B") << 16) |
                    (self.readFormat("B") << 8) | self.readFormat("B")) & 0x7FFFFFFFFFFFFFF
        elif (case == 0x1F):
            if (case & 7) == 0:
                return (byte << 40 | (self.readFormat("B") << 32) |
                        (self.readFormat("B") << 24) | (self.readFormat("B") << 16) |
                        (self.readFormat("B") << 8) | self.readFormat("B")) & 0xFFFFFFFFFF
            elif (case & 7) == 1:
                return (self.readFormat("B") << 56 | (self.readFormat("B") << 48) |
                        (self.readFormat("B") << 40) | (self.readFormat("B") << 32) |
                        (self.readFormat("B") << 24) | (self.readFormat("B") << 16) |
                        (self.readFormat("B") << 8) | self.readFormat("B"))
        return 0

    def getType(self, name):
        for typ in self.types[1:]:
            if typ.name == name:
                return typ

    def getItem(self, typ):
        if isinstance(typ, str):
            typ = self.getType(typ)

        for item in self.items:
            if item.typ == typ:
                return item

    def getObject(self, index):
        item = self.items[index + 1]

        if item.typ == None:
            return None

        if item.value == None:
            item.value = [self.readObject(item.typ,
                                          item.offset + x * item.typ.superType.byteSize)
                          for x in xrange(item.count)]

        return item.value[0]


class TagSectionWriter(object):
    def __init__(self, w, signature, flag=True):
        self.w = w
        self.headerOffset = w.f.tell()
        self.flag = flag

        w.writeFormat(">I", 0)
        w.f.write(signature[:4])

    def __enter__(self):
        self.w.f.seek(self.headerOffset + 8)
        return self

    def __exit__(self, arg1, arg2, arg3):
        self.w.pad(4)

        endOffset = self.w.f.tell()

        self.w.f.seek(self.headerOffset)
        if self.flag:
            self.w.writeFormat(">I", 0x40000000 | (endOffset - self.headerOffset))
        else:
            self.w.writeFormat(">I", endOffset - self.headerOffset)

        self.w.f.seek(endOffset)


class TagWriter(object):
    def __init__(self, f):
        self.f = f
        self.dataOffset = 0
        self.types = [None]
        self.items = [None]
        self.items2 = []
        self.patches = {}

    def __enter__(self):
        return self

    def __exit__(self, arg1, arg2, arg3):
        self.f.close()

    @staticmethod
    def toFile(outputFileName, obj):
        with TagWriter(open(outputFileName, "wb")) as w:
            w.writeRootSection(obj)

    def writeTypeSection(self):
        with TagSectionWriter(self, "TYPE", False) as t1:

            with TagSectionWriter(self, "TPTR") as t2:
                self.writeNulls(8 * len(self.types))

            typeStrings = []
            fieldStrings = []
            for typ in self.types[1:]:
                if not typ.name in typeStrings:
                    typeStrings.append(typ.name)

                for template in typ.templates:
                    if not template.name in typeStrings:
                        typeStrings.append(template.name)

                for member in typ.members:
                    if not member.name in fieldStrings:
                        fieldStrings.append(member.name)

            with TagSectionWriter(self, "TSTR") as t3:
                self.f.write("\0".join(typeStrings) + "\0")

            with TagSectionWriter(self, "TNAM") as t4:
                self.writePacked(len(self.types))

                for typ in self.types[1:]:
                    self.writePacked(typeStrings.index(typ.name))
                    self.writePacked(len(typ.templates))

                    for template in typ.templates:
                        self.writePacked(typeStrings.index(template.name))
                        self.writePacked(self.types.index(template.value) if template.isType else template.value)

            with TagSectionWriter(self, "FSTR") as t5:
                self.f.write("\0".join(fieldStrings) + "\0")

            with TagSectionWriter(self, "TBOD") as t6:
                for typ in self.types[1:]:
                    self.writePacked(self.types.index(typ))
                    self.writePacked(self.types.index(typ.parent))
                    self.writePacked(typ.flags)

                    if typ.flags & TagFlag.SubType:
                        self.writePacked(typ.subTypeFlags)

                    if typ.flags & TagFlag.Pointer:
                        self.writePacked(self.types.index(typ.pointer))

                    if typ.flags & TagFlag.Version:
                        self.writePacked(typ.version)

                    if typ.flags & TagFlag.ByteSize:
                        self.writePacked(typ.byteSize)
                        self.writePacked(typ.alignment)

                    if typ.flags & TagFlag.AbstractValue:
                        self.writePacked(typ.abstractValue)

                    if typ.flags & TagFlag.Members:
                        self.writePacked(len(typ.members))

                        for member in typ.members:
                            self.writePacked(fieldStrings.index(member.name))
                            self.writePacked(member.flags)
                            self.writePacked(member.byteOffset)
                            self.writePacked(self.types.index(member.typ))

                    if typ.flags & TagFlag.Interfaces:
                        self.writePacked(len(typ.interfaces))

                        for typ, flag in typ.interfaces:
                            self.writePacked(self.types.index(typ))
                            self.writePacked(flag)

            with TagSectionWriter(self, "THSH") as t7:
                hashes = [x for x in self.types[1:] if x.hsh]

                self.writePacked(len(hashes))

                for typ in hashes:
                    self.writePacked(self.types.index(typ))
                    self.writeFormat("<I", typ.hsh)

            with TagSectionWriter(self, "TPAD") as t8:
                pass

    def writeIndexSection(self):
        with TagSectionWriter(self, "INDX", False) as t1:

            with TagSectionWriter(self, "ITEM") as t2:
                self.writeNulls(12)

                for item in self.items[1:]:
                    if item.isPtr:
                        self.writeFormat("<I", self.types.index(item.typ) | 0x10000000)
                    else:
                        self.writeFormat("<I", self.types.index(item.typ) | 0x20000000)

                    self.writeFormat("<I", item.offset - self.dataOffset)
                    self.writeFormat("<I", len(item.value))

            with TagSectionWriter(self, "PTCH") as t3:
                patches = [(self.types.index(key), value)
                           for key, value in self.patches.iteritems()]

                patches.sort(key=lambda x: x[0])

                for typ, offsets in patches:
                    offsets = list(set(offsets))
                    offsets.sort()

                    self.writeFormat("<2I", typ, len(offsets))

                    for offset in offsets:
                        self.writeFormat("<I", offset - self.dataOffset)

    def nextPowerOfTwo(self, n):
        if (n == 1):
            return 2

        n -= 1
        n |= n >> 1
        n |= n >> 2
        n |= n >> 4
        n |= n >> 8
        n |= n >> 16
        n += 1
        return n

    def writeRootSection(self, obj):
        self.scanObjectForType(obj)
        self.makeItem(obj, True)

        with TagSectionWriter(self, "TAG0", False) as t1:

            with TagSectionWriter(self, "SDKV") as t2:
                self.f.write("20160100")

            with TagSectionWriter(self, "DATA") as t3:
                self.dataOffset = t3.headerOffset + 8

                while len(self.items2):
                    items3 = self.items2
                    self.items2 = []

                    for item in items3:
                        self.pad(self.nextPowerOfTwo(item.typ.superType.alignment))

                        item.offset = self.f.tell()
                        for i in xrange(len(item.value)):
                            self.writeObject(item.value[i], item.offset + i * item.typ.superType.byteSize)

                self.pad(16)

            self.writeTypeSection()
            self.writeIndexSection()

    def writeObject(self, obj, offset=0):
        if offset == 0:
            offset = self.f.tell()

        else:
            self.f.seek(offset)

        typ = obj.typ.superType

        if typ.subType == TagSubType.Bool:
            self.writeFormat(TagReader.getFormatString(typ.mFormatInfo), obj.value)

        elif typ.subType == TagSubType.String or typ.subType == TagSubType.Pointer or typ.subType == TagSubType.Array:

            item = self.makeItem(obj)
            if item != None:
                self.addPatch(typ)
                self.writeFormat("<I", self.items.index(item))

        elif typ.subType == TagSubType.Int:
            self.writeFormat(TagReader.getFormatString(typ.mFormatInfo, obj.value < 0), obj.value)

        elif typ.subType == TagSubType.Float:
            self.writeFormat("<f", obj.value)

        elif typ.subType == TagSubType.Class:
            for member in typ.allMembers:
                if obj.value.has_key(member.name):
                    self.writeObject(obj.value[member.name], offset + member.byteOffset)

        elif typ.subType == TagSubType.Tuple:
            for i in xrange(typ.tupleSize):
                self.writeObject(obj.value[i], offset + i * typ.mSubType.superType.byteSize)

        self.f.seek(offset + typ.byteSize)

    def addPatch(self, typ):
        if self.patches.has_key(typ):
            self.patches[typ].append(self.f.tell())

        else:
            self.patches[typ] = [self.f.tell()]

    def writeFormat(self, format, *args):
        self.f.write(struct.pack(format, *args))

    def writePacked(self, value):
        if value < 0x80:
            self.writeFormat("B", value)
        elif value < 0x4000:
            self.writeFormat(">H", value | 0x8000)
        elif value < 0x200000:
            self.writeFormat("B", (value >> 16) | 0xc0)
            self.writeFormat(">H", value & 0xffff)
        elif value < 0x8000000:
            self.writeFormat(">I", value | 0xe0000000)

    def writeNulls(self, amount):
        self.f.write("\0" * amount)

    def pad(self, alignment):
        amount = alignment - self.f.tell() % alignment

        if amount != alignment:
            self.writeNulls(amount)

    def makeItem(self, obj, pointer=False):
        if obj.value == None or (hasattr(obj.value, "__len__") and len(obj.value) <= 0):
            return None

        if obj.attachment != None:
            return obj.attachment

        item = TagItem()

        if obj.typ.superType.subType == TagSubType.String:
            item.typ = self.getType("char")
            item.value = [TagObject(ord(x), item.typ) for x in obj.value + "\0"]

        elif obj.typ.superType.subType == TagSubType.Pointer or pointer:
            # Fake Pointer
            if obj.typ.superType.subType == TagSubType.Class:
                item.typ = obj.typ
                item.value = [obj]
                item.isPtr = True

            else:
                item.typ = obj.value.typ
                item.value = [obj.value]
                item.isPtr = True

        elif obj.typ.superType.subType == TagSubType.Array:
            item.typ = obj.typ.superType.mSubType
            item.value = obj.value

            if item.typ.superType.subType == TagSubType.Pointer:
                item.isPtr = True

        else:
            return None

        obj.attachment = item

        self.items.append(item)
        self.items2.append(item)

        return item

    def scanType(self, typ):
        if typ != None and not typ in self.types:
            self.types.append(typ)

            for template in typ.templates:
                if template.isType:
                    self.scanType(template.value)

            self.scanType(typ.parent)
            self.scanType(typ.mSubType)

            for member in typ.members:
                self.scanType(member.typ)

            for iTyp, flag in typ.interfaces:
                self.scanType(iTyp)

    def scanObjectForType(self, obj):
        if obj == None:
            return

        self.scanType(obj.typ)

        if obj.typ.superType.subType == TagSubType.Pointer:
            self.scanObjectForType(obj.value)

        elif obj.typ.superType.subType == TagSubType.Class:
            for member in obj.typ.allMembers:
                if obj.value.has_key(member.name):
                    self.scanObjectForType(obj.value[member.name])

        elif obj.typ.superType.subType & 0xF == TagSubType.Array:
            for obj2 in obj.value:
                self.scanObjectForType(obj2)

    def getType(self, name):
        for typ in self.types[1:]:
            if typ.name == name:
                return typ


class TagTypeHelper(object):
    @staticmethod
    def getAttrib(elem, name, default=None, method=None):
        if elem.attrib.has_key(name):
            attribValue = elem.attrib[name]

            if method != None:
                return method(attribValue)

            else:
                return attribValue

        else:
            return default

    @staticmethod
    def loadTypes(inputFileName):
        rootElem = ET.parse(inputFileName)
        typeElems = list(rootElem.findall("type"))
        typeElems.sort(key=lambda x: int(x.get("id")))
        types = [None] + [TagType() for x in typeElems]

        for i in xrange(1, len(types)):
            typ = types[i]
            typeElem = typeElems[i - 1]

            typ.name = TagTypeHelper.getAttrib(typeElem, "name", "")
            typ.parent = types[TagTypeHelper.getAttrib(typeElem, "parent", 0, int)]
            typ.flags = TagTypeHelper.getAttrib(typeElem, "flags", 0, int)
            typ.mFormatInfo = TagTypeHelper.getAttrib(typeElem, "subTypeFlags", 0, int)
            typ.mSubType = types[TagTypeHelper.getAttrib(typeElem, "pointer", 0, int)]
            typ.version = TagTypeHelper.getAttrib(typeElem, "version", 0, int)
            typ.byteSize = TagTypeHelper.getAttrib(typeElem, "byteSize", 0, int)
            typ.alignment = TagTypeHelper.getAttrib(typeElem, "alignment", 0, int)
            typ.abstractValue = TagTypeHelper.getAttrib(typeElem, "abstractValue", 0, int)
            typ.hsh = TagTypeHelper.getAttrib(typeElem, "hash", 0, int)

            for tempElem in typeElem.findall("template"):
                template = TagTemplate(
                    TagTypeHelper.getAttrib(tempElem, "name", "v"),
                    TagTypeHelper.getAttrib(tempElem, "value", 0, int))

                if template.isType:
                    template.value = types[template.value]

                typ.templates.append(template)

            for memberElem in typeElem.findall("member"):
                member = TagMember()
                member.name = TagTypeHelper.getAttrib(memberElem, "name", "")
                member.flags = TagTypeHelper.getAttrib(memberElem, "flags", 0, int)
                member.byteOffset = TagTypeHelper.getAttrib(memberElem, "offset", 0, int)
                member.typ = types[TagTypeHelper.getAttrib(memberElem, "type", 0, int)]
                typ.members.append(member)

            for interfaceElem in typeElem.findall("interface"):
                typ.interfaces.append((
                    types[TagTypeHelper.getAttrib(interfaceElem, "type", 0, int)],
                    TagTypeHelper.getAttrib(interfaceElem, "flags", 0, int)))

        return types[1:]


class TagXmlParser(object):
    def __init__(self, rootElem, types):
        self.types = types
        self.objectElems = list(rootElem.findall("object"))
        self.objects = [None] + [TagObject(None, None) for x in xrange(len(self.objectElems))]
        self.objectElems.sort(key=lambda x: self.parseObjId(x.get("id")))

    @staticmethod
    def fromFile(inputFileName, types, objName="hkRootLevelContainer"):
        return TagXmlParser(ET.parse(inputFileName), types).findObject(objName)

    def findType(self, name):
        name = name.replace("::", "")

        for typ in self.types:
            if typ and typ.name.replace("::", "") == name:
                return typ

    def findObject(self, name):
        if isinstance(name, TagType):
            name = name.name

        name = name.replace("::", "")

        for i in xrange(len(self.objectElems)):
            if self.objectElems[i].get("type") == name:
                return self.parseObject(i + 1)

    def parseObjId(self, val):
        if val.startswith("#"):
            return int(val[1:])

        return 0

    def parseFloat(self, text):
        return struct.unpack("f", struct.pack("I", int(text[1:], 16)))[0]

    def splitNumArray(self, text):
        prettyString = text.strip().replace("\n", "").replace("\r", "")
        return [x for x in prettyString.split(" ") if x]

    def parseNumArray(self, typ, text):
        return [self.parseValueText(typ, x) for x in self.splitNumArray(text)]

    def parseArray(self, typ, elem):
        pointer = typ.superType.mSubType.superType

        value = None
        if pointer.subType >= TagSubType.Bool and pointer.subType <= TagSubType.Float and pointer.subType != TagSubType.String:
            value = self.parseNumArray(typ.superType.mSubType, elem.text)

        else:
            value = [self.parseValue(typ.superType.mSubType, x) for x in elem]

        return TagObject([x for x in value if x], typ)

    def parseValueText(self, typ, text):
        value = None

        if typ.superType.subType == TagSubType.Bool:
            value = bool(text)

        elif typ.superType.subType == TagSubType.Int:
            if typ.superType.mFormatInfo & TagSubType.Int64:
                value = long(text)
            else:
                value = int(text)

        elif typ.superType.subType == TagSubType.Float:
            value = self.parseFloat(text)

        return TagObject(value, typ)

    def parseValue(self, typ, elem):
        if typ.superType.subType == TagSubType.String:
            return TagObject(elem.text, typ)

        elif typ.superType.subType >= TagSubType.Bool and typ.superType.subType <= TagSubType.Float:
            return self.parseValueText(typ, elem.text)

        elif typ.superType.subType == TagSubType.Pointer:
            return TagObject(self.parseObject(self.parseObjId(elem.text)), typ)

        elif typ.superType.subType == TagSubType.Class:
            members = {x.name: x for x in typ.superType.allMembers}

            for memberElem in elem:
                name = memberElem.get("name")
                value = self.parseValue(members[name].typ, memberElem)

                # Any invalid type: death sentence
                if value == None or value.value == None or value.typ == None:
                    return None

                members[name] = value

            if typ.superType.name == "hkQsTransformf":
                floats = [TagObject(self.parseFloat(x), self.findType("float")) for x in self.splitNumArray(elem.text)]

                members["translation"] = TagObject(floats[:4], members["translation"].typ)
                members["rotation"] = TagObject(floats[4:8], members["rotation"].typ)
                members["scale"] = TagObject(floats[8:12], members["scale"].typ)

            return TagObject({x: y for x, y in members.iteritems() if isinstance(y, TagObject)}, typ)

        elif typ.superType.subType & 0xF == TagSubType.Array:
            return self.parseArray(typ, elem)

    def parseObject(self, index):
        obj = self.objects[index]
        objElem = self.objectElems[index - 1]

        if obj.value == None or obj.typ == None:
            typ = self.findType(objElem.get("type"))

            if typ == None:
                print "WARNING: Type '{}' could not be found in the type database!".format(objElem.get("type"))
                return

            obj2 = self.parseValue(typ, objElem)

            obj.value = obj2.value
            obj.typ = obj2.typ

        return obj


TagXmlSerializerSpecialTypeNames = {
    "hkcdStaticTreeDynamicStoragehkcdStaticTreeCodec3Axis4": "hkcdStaticTreeDynamicStorage4",
    "hkcdStaticTreeDynamicStoragehkcdStaticTreeCodec3Axis5": "hkcdStaticTreeDynamicStorage5",
    "hkcdStaticTreeDynamicStoragehkcdStaticTreeCodec3Axis6": "hkcdStaticTreeDynamicStorage6",
    "hkcdStaticTreeTreehkcdStaticTreeDynamicStorage6": "hkcdStaticTreeDefaultTreeStorage6"
}


class TagXmlSerializer(object):
    def __init__(self, backporter=None):
        self.types = []
        self.objects = []
        self.objCounter = 0
        self.backporter = backporter

    @staticmethod
    def toFile(outputFileName, obj, backporter=None):
        with open(outputFileName, "w") as f:
            f.write('<?xml version="1.0" encoding="ascii"?>\n')
            # print("serializing")
            serialized = TagXmlSerializer(backporter).serialize(obj)
            # print("serialize finished, writing...")
            ET.ElementTree(serialized).write(f)
            # print("wrote to " + outputFileName)

    def getIdString(self, index):
        return "#{:04}".format(index)

    def getTypeName(self, typ, dontCare=False):
        if typ.superType is not None:
            typ = typ.superType

        if not dontCare and typ.tag != None:
            return typ.tag

        name = typ.name

        for template in typ.templates:
            if template.isType:
                # print("find type: " + typ.name)
                # print("template: " + str(template))
                # print("template: " + str(template.value))
                # print("template: " + str(template.value.name))
                # print("template: " + str(template.value.tag))
                # print("template val: " + template.value.name + " and got: " + self.getTypeName(template.value))
                name += self.getTypeName(template.value)
            else:
                name += str(template.value)

        ret = name.replace(":", "").replace(" ", "")

        if dontCare:
            return ret

        typ.tag = ret
        return typ.tag

    def getSubTypeName(self, typ):
        typ = typ.superType

        if typ.subType == TagSubType.Bool or typ.subType == TagSubType.Int:
            if typ.mFormatInfo & TagSubType.Int8:
                return "byte"
            else:
                return "int"

        elif typ.subType == TagSubType.String:
            return "string"

        elif typ.subType == TagSubType.Float:
            return "real"

        elif typ.subType == TagSubType.Pointer:
            return "ref"

        elif typ.subType == TagSubType.Class:
            return "struct"

        elif typ.subType == TagSubType.Array:
            return "array"

        elif typ.subType == TagSubType.Tuple:
            return "tuple"

        return ""

    def getFloatString(self, value):
        return "x{:08x}".format(struct.unpack("I", struct.pack("f", value))[0])

    def getValueString(self, obj):
        typ = obj.typ.superType

        if typ.subType == TagSubType.Bool:
            return str(1 if obj.value else 0)

        elif typ.subType == TagSubType.Int:
            return str(obj.value)

        elif typ.subType == TagSubType.Float:
            return self.getFloatString(obj.value)

    def makeNumArray(self, obj):
        index = 16 if obj.typ.superType.mSubType.superType.byteSize == 1 else 8

        result = ""
        for i in xrange(len(obj.value)):
            if not i % index:
                result += "\n"

            result += self.getValueString(obj.value[i]) + " "

        return result[:-1]

    def serializeObject(self, parent, obj):
        if (hasattr(obj.value, "__len__") and len(obj.value) > 0) or obj.value:
            elem = ET.SubElement(parent, self.getSubTypeName(obj.typ))

            typ = obj.typ.superType

            if typ.subType == TagSubType.Bool:
                elem.text = str(1 if obj.value else 0)

            elif typ.subType == TagSubType.String:
                elem.text = obj.value

            elif typ.subType == TagSubType.Int:
                elem.text = str(obj.value)

            elif typ.subType == TagSubType.Float:
                elem.text = self.getFloatString(obj.value)

            elif typ.subType == TagSubType.Pointer:
                elem.text = self.getIdString(obj.value.attachment)

            elif typ.subType == TagSubType.Class:
                # hkQsTransformf
                if typ.name == "hkQsTransformf":
                    floats = [x.value for x in
                              obj.value["translation"].value + obj.value["rotation"].value + obj.value["scale"].value]

                    elem.tag = "vec12"
                    elem.text = " ".join([self.getFloatString(x) for x in floats])

                else:
                    for member in typ.allMembers:
                        if not member.flags & 1 and obj.value.has_key(member.name):
                            memberElem = self.serializeObject(elem, obj.value[member.name])

                            if memberElem != None:
                                memberElem.set("name", member.name)

                            if member.tag:
                                memberElem.tag = self.getSubTypeName(member.tag)

            elif typ.subType & 0xF == TagSubType.Array:
                pointer = typ.mSubType.superType

                if pointer.subType == TagSubType.Bool or pointer.subType == TagSubType.Int:
                    elem.text = self.makeNumArray(obj)

                elif pointer.subType == TagSubType.Float:
                    elem.text = " ".join([self.getFloatString(x.value) for x in obj.value])

                else:
                    for obj2 in obj.value:
                        self.serializeObject(elem, obj2)

                if typ.subType == TagSubType.Array:
                    elem.set("size", str(len(obj.value)))

                elif typ.subType == TagSubType.Tuple:
                    elem.set("size", str(typ.tupleSize))

                # hkVector4
                if typ.tupleSize == 4 and pointer.subType == TagSubType.Float:
                    elem.tag = "vec4"
                    elem.attrib.pop("size")

                # hkMatrix4f
                elif typ.tupleSize == 16 and pointer.subType == TagSubType.Float:
                    elem.tag = "vec16"
                    elem.attrib.pop("size")

            return elem

    def serializeMemberProp(self, parent, typ):
        if typ == None:
            return

        typ = typ.superType

        parent.set("type", self.getSubTypeName(typ))

        if typ.subType == TagSubType.Pointer:
            parent.set("class", self.getTypeName(typ.mSubType))

        elif typ.subType == TagSubType.Class:
            if typ.name == "hkQsTransformf":
                parent.set("type", "vec12")

            else:
                parent.set("class", self.getTypeName(typ))

        elif typ.subType == TagSubType.Array:
            parent.set("array", "true")
            self.serializeMemberProp(parent, typ.mSubType)

        elif typ.subType == TagSubType.Tuple:
            if typ.mSubType.superType.subType == TagSubType.Float and typ.tupleSize == 4:
                parent.set("type", "vec4")

            elif typ.mSubType.superType.subType == TagSubType.Float and typ.tupleSize == 16:
                parent.set("type", "vec16")

            else:
                parent.set("count", str(typ.tupleSize))
                self.serializeMemberProp(parent, typ.mSubType)

    def serializeType(self, parent, typ):
        elem = ET.SubElement(parent, "class")

        # print("Serializing Type " + typ.name)
        elem.set("name", self.getTypeName(typ, True))
        elem.set("version", str(typ.version))

        if typ.parent != None:
            elem.set("parent", self.getTypeName(typ.parent))

        for member in typ.members:
            # print("    Serializing Member " + member.name + " : " + self.getSubTypeName(member.typ))
            # if typ.name == "hkRootLevelContainer::NamedVariant":
            #     print( "       hkRootLevelContainer::NamedVariant " + str(member.tag) + " || " + self.getSubTypeName(member.typ))
            #     print( "           || " + str(member.typ.superType.name) + "   " + str(member.typ.superType.subType))
            memberElem = ET.SubElement(elem, "member")
            memberElem.set("name", member.name)
            self.serializeMemberProp(memberElem, member.tag if member.tag else member.typ)

            if member.flags & 1:
                memberElem.set("type", "void")

        return elem

    def serialize(self, obj):
        self.objects.append(obj)
        self.objCounter += 1
        obj.attachment = self.objCounter
        self.scanObjectForType(obj)

        if self.backporter != None:
            self.backporter(self.types)

        rootElem = ET.Element("hktagfile", {"version": "1", "sdkversion": "hk_2012.2.0-r1"})

        for typ in self.types:
            if typ.subType == TagSubType.Class and typ.name != "hkQsTransformf":
                self.serializeType(rootElem, typ)

        for obj2 in self.objects:
            elem = self.serializeObject(rootElem, obj2)
            elem.set("id", self.getIdString(obj2.attachment))
            elem.set("type", self.getTypeName(obj2.typ.superType))
            elem.tag = "object"

        TagXmlSerializer.indent(rootElem)
        return rootElem

    @staticmethod
    def indent(elem, level=0, hor="  ", ver="\n"):
        i = ver + level * hor
        if len(elem):
            if not elem.text or not elem.text.strip():
                elem.text = i + hor
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
            for elem in elem:
                TagXmlSerializer.indent(elem, level + 1, hor, ver)
            if not elem.tail or not elem.tail.strip():
                elem.tail = i
        else:
            if level and (not elem.tail or not elem.tail.strip()):
                elem.tail = i
                if elem.text and elem.text.startswith("\n"):
                    elem.text = elem.text.replace("\n", i + hor) + i
                elif (elem.tag == "class" or elem.tag == "struct") and not len(elem):
                    elem.text = i


    def scanType(self, typ):
        if typ is None:
            return
        if typ not in self.types:
            self.types.append(typ)
            # if typ in self.typesCheckedObjects:
            #     return
            # else:
            #     self.typesCheckedObjects.append(typ)
            # # debug("type not recorded", typ.name)
            if typ.name == "T*":
                # debug("checking T*")
                return
            self.scanType(typ.parent)
            self.scanType(typ.mSubType)

            # debug("record type", typ.name)

            for member in typ.members:
                self.scanType(member.typ)

            self.getTypeName(typ)

            if TagXmlSerializerSpecialTypeNames.has_key(typ.tag):
                specialName = TagXmlSerializerSpecialTypeNames[typ.tag]

                # Create Fake Type
                fakeType = TagType(specialName)
                fakeType.mFormatInfo = 7
                fakeType.tag = specialName
                fakeType.parent = TagType(typ.tag)
                self.types.append(fakeType)

                typ.tag = specialName
        else:
            pass
            # debug("type already recorded", typ.name)

    def scanObjectForType(self, obj):
        if obj == None:
            return

        # while True:
        self.scanType(obj.typ)
        # if obj.value is None:
        #     break

        if obj.typ.superType.subType == TagSubType.Pointer and obj.value and not obj.value.attachment:
            self.objects.append(obj.value)
            self.objCounter += 1
            obj.value.attachment = self.objCounter

            self.scanObjectForType(obj.value)
        elif obj.typ.superType.subType == TagSubType.Class:
            for member in obj.typ.allMembers:
                if obj.value.has_key(member.name):
                    self.scanObjectForType(obj.value[member.name])

        elif obj.typ.superType.subType & 0xF == TagSubType.Array:
            for obj2 in obj.value:
                self.scanObjectForType(obj2)
        # else:
        #     break

def findFile(fileName):
    for arg in sys.argv:
        path = os.path.join(os.path.dirname(arg), fileName)

        if os.path.exists(path):
            return path

    raise ValueError("{} could not be found.".format(fileName))


class TagTypeBackporter(object):
    @staticmethod
    def findMember(typ, name):
        for member in typ.members:
            if member.name == name:
                return member

    @staticmethod
    def findType(types, name):
        for typ in types:
            if typ.name == name:
                return typ

    @staticmethod
    def removeMemberFromType(typ, mem):
        if mem is not None:
            typ.members.remove(mem)


    @staticmethod
    def backportTypes2012(types):
        # hkReferencedObject
        typ = TagTypeBackporter.findType(types, "hkReferencedObject")
        if typ != None and typ.version > 0:
            typ.version = 0
            typ.members.remove(TagTypeBackporter.findMember(typ, "propertyBag"))
            TagTypeBackporter.findMember(typ, "refCount").name = "referenceCount"

            # Remove anything related to property bag.
            for typ in list(types):
                if typ.name == "hkDefaultPropertyBag" or \
                        typ.name.startswith("hkHash") or \
                        typ.name == "hkTuple" or \
                        typ.name == "hkPropertyId" or \
                        typ.name == "hkPtrAndInt" or \
                        typ.name == "hkPropertyDesc":
                    types.remove(typ)

        # hkxMeshSection
        typ = TagTypeBackporter.findType(types, "hkxMeshSection")
        if typ != None and typ.version > 4:
            typ.version = 4
            typ.members.remove(TagTypeBackporter.findMember(typ, "boneMatrixMap"))

        # hkxVertexBuffer::VertexData
        typ = TagTypeBackporter.findType(types, "hkxVertexBuffer::VertexData")
        if typ != None and typ.version > 0:
            typ.version = 0

        # hkxVertexDescription::ElementDecl
        typ = TagTypeBackporter.findType(types, "hkxVertexDescription::ElementDecl")
        if typ != None and typ.version > 3:
            typ.version = 3
            TagTypeBackporter.removeMemberFromType(typ, TagTypeBackporter.findMember(typ, "channelID"))

        # hkxMaterial
        typ = TagTypeBackporter.findType(types, "hkxMaterial")
        if typ != None and typ.version > 4:
            typ.version = 4
            typ.members.remove(TagTypeBackporter.findMember(typ, "userData"))

        # hkaSkeleton
        typ = TagTypeBackporter.findType(types, "hkaSkeleton")
        if typ != None and typ.version > 5:
            typ.version = 5

        # hkcdStaticMeshTreeBase
        typ = TagTypeBackporter.findType(types, "hkcdStaticMeshTreeBase")
        if typ != None and typ.version > 0:
            typ.version = 0
            typ.members.remove(TagTypeBackporter.findMember(typ, "primitiveStoresIsFlatConvex"))

        # hkaInterleavedUncompressedAnimation
        typ = TagTypeBackporter.findType(types, "hkaInterleavedUncompressedAnimation")
        if typ != None and typ.version > 0:
            typ.version = 0

        # hkpStaticCompundShape
        typ = TagTypeBackporter.findType(types, "hkpStaticCompoundShape")
        if typ != None:
            TagTypeBackporter.findMember(typ, "numBitsForChildShapeKey").tag = TagTypeBackporter.findMember(typ,
                                                                                                            "instanceExtraInfos").typ.mSubType

        # hkpStaticCompoundShape::Instance
        typ = TagTypeBackporter.findType(types, "hkpStaticCompoundShape::Instance")
        if typ != None and typ.version > 0:
            typ.version = 0

        return types


def findFile(fileName, mandatory=True):
    for arg in sys.argv:
        path = os.path.join(os.path.dirname(arg), fileName)

        if os.path.exists(path):
            return path

    if mandatory:
        raise ValueError("AssetCc2.exe could not be found.")

    return None


if __name__ == "__main__":
    if len(sys.argv) <= 1:
        print "Tool for converting HKX (version <= 2012 2.0) files to 2016 1.0 tag binary files, and vice versa."
        print "\nUsage: {} [source] [compendium] [destination]".format(os.path.basename(sys.argv[0]))
        print "Compendium file is needed for files that contain no type info."
        print "If no destination is included, the changes will be overwritten to the source."
        print "You can do a simple drag and drop that way."
        print "\nMade by Skyth."
        print "Press enter to continue..."
        raw_input()

    else:
        inputFileName = None
        inputFileType = TagFileType.Invalid
        compendiumFileName = None
        outputFileName = None

        for arg in sys.argv[1:]:
            if (os.path.exists(arg)):
                typ = TagReader.checkFile(arg)
            else:
                typ = TagFileType.Invalid

            if (compendiumFileName == None and typ == TagFileType.Compendium):
                compendiumFileName = arg
            elif (inputFileName == None):
                inputFileName = arg
                inputFileType = typ
            elif (outputFileName == None):
                outputFileName = arg

        if (outputFileName == None):
            outputFileName = os.path.splitext(inputFileName)[0] + ".hkx"

        tempFileName = os.path.join(os.path.dirname(sys.argv[0]), "temp.xml")
        # print(tempFileName)
        print("input file type", inputFileType)
        if inputFileType == TagFileType.Object:
            assetCc2Path = findFile("AssetCc2.exe", False)

            destinationFileName = tempFileName
            if (assetCc2Path == None):
                destinationFileName = outputFileName
            debug("dest: " + destinationFileName)
            parsedObj = TagReader.fromFile(inputFileName, compendiumFileName)
            TagXmlSerializer.toFile(destinationFileName, parsedObj, TagTypeBackporter.backportTypes2012)

            if (assetCc2Path != None):
                # subprocess.call([assetCc2Path, "--strip", "--rules8011", tempFileName, outputFileName])
                subprocess.call([assetCc2Path, "--strip", "--rules4101", tempFileName, outputFileName])
                # print("assetCc to " + outputFileName)
        else:
            types = TagTypeHelper.loadTypes(findFile("TypeDatabase.xml"))
            subprocess.call([findFile("AssetCc2.exe"), "-g", "-x", inputFileName, tempFileName])
            TagWriter.toFile(outputFileName, TagXmlParser.fromFile(tempFileName, types))

        if os.path.exists(tempFileName):
            os.remove(tempFileName)
