using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Text;
using Havoc.Extensions;
using Havoc.IO.Tagfile.Binary.Sections;
using Havoc.IO.Tagfile.Binary.Types;
using Havoc.Objects;
using Havoc.Reflection;

namespace Havoc.IO.Tagfile.Binary
{
    public class HkBinaryTagfileReader : IDisposable {
        private readonly string CompendiumPath;
        private List<ulong> mCompendiumIDs;

        private readonly bool mLeaveOpen;
        private readonly BinaryReader mReader;
        private readonly Stream mStream;
        private long mDataOffset;
        private List<Item> mItems;
        private List<HkType> mTypes;

        private HkBinaryTagfileReader( Stream stream, string compendium, bool leaveOpen )
        {
            CompendiumPath = compendium;
            mStream = stream;
            mReader = new BinaryReader( mStream, Encoding.UTF8, true );
            mLeaveOpen = leaveOpen;
        }

        public void Dispose()
        {
            if ( !mLeaveOpen )
                mStream.Dispose();

            mReader.Dispose();
        }

        private void ReadTagSection( HkSection section )
        {
            foreach ( var subSection in section.SubSections )
                switch ( subSection.Signature )
                {
                    case "TCRF": {
                        mStream.Seek( subSection.Position, SeekOrigin.Begin );
                        var compId = mReader.ReadUInt64();
                        // Read 8 as Compendium ID
                        if (CompendiumPath == "") {
                            throw new InvalidDataException("TCRF found but Compendium is empty");
                        }

                        if (!mCompendiumIDs.Contains(compId)) {
                            throw new InvalidDataException($"TCRF ref comp id {compId} but not found");
                        }
                        break;
                    }
                    case "SDKV":
                    {
                        mStream.Seek( subSection.Position, SeekOrigin.Begin );

                        string sdkVersion = mReader.ReadString( 8 );
                        if ( !HkSdkVersion.SupportedSdkVersions.Contains( new HkSdkVersion( sdkVersion ) ) )
                            throw new NotSupportedException( $"Unsupported SDK version: {sdkVersion}" );
                        break;
                    }

                    case "DATA":
                        mDataOffset = subSection.Position;
                        break;

                    case "TYPE":
                        if (CompendiumPath != "") {
                            break;
                            // throw new InvalidDataException("Types found in HKX, but expected to be in Compendium)");
                        }
                        ReadTypeSection( subSection );
                        break;

                    case "INDX":
                        ReadIndexSection( subSection );
                        break;

                    default:
                        throw new InvalidDataException( $"Unexpected signature: {subSection.Signature}" );
                }
        }

        private void ReadTypeCompendiumSection( HkSection section )
        {
            // Very barebones
            foreach ( var subSection in section.SubSections )
                switch ( subSection.Signature )
                {
                    case "TCID":
                        ReadIDsSection( subSection );
                        break;

                    case "TYPE":
                        ReadTypeSection( subSection );
                        break;

                    default:
                        throw new InvalidDataException( $"Unexpected signature: {subSection.Signature}" );
                }
        }

        private void ReadIDsSection( HkSection section ) {
            mCompendiumIDs = new List<ulong>();
            if (section.Length % 8 != 0) {
                throw new InvalidDataException($"TCID length {section.Length} can't be mod by 8");
            }

            mReader.BaseStream.Seek( section.Position, SeekOrigin.Begin );
            for (int i = 0; i < section.Length / 8; i++) {
                mCompendiumIDs.Add(mReader.ReadUInt64());
            }
        }

        private void ReadTypeSection( HkSection section )
        {
            mTypes = HkBinaryTypeReader.ReadTypeSection( mReader, section );
        }

        private void ReadIndexSection( HkSection section )
        {
            foreach ( var subSection in section.SubSections )
                switch ( subSection.Signature )
                {
                    case "ITEM":
                    {
                        mStream.Seek( subSection.Position, SeekOrigin.Begin );

                        mItems = new List<Item>( ( int ) ( subSection.Length / 24 ) );
                        while ( mStream.Position < subSection.Position + subSection.Length )
                            mItems.Add( new Item( this ) );

                        break;
                    }

                    case "PTCH":
                        break;

                    default:
                        throw new InvalidDataException( $"Unexpected signature: {subSection.Signature}" );
                }
        }

        private void ReadCompendium() {
            if (CompendiumPath != "") {
                var compendiums = ReadCompendiums(CompendiumPath);
                mTypes = compendiums.mTypes;
                mCompendiumIDs = compendiums.mCompendiumIDs;
                // mCompendiumIDs.ForEach(Console.WriteLine);
            }
        }

        private void ReadRootSection()
        {
            var section = new HkSection( mReader );
            switch ( section.Signature )
            {
                case "TAG0":
                    ReadTagSection( section );
                    break;

                case "TCM0":
                    ReadTypeCompendiumSection( section );
                    break;

                default:
                    throw new InvalidDataException( $"Unexpected signature: {section.Signature}" );
            }
        }

        public static IHkObject Read( Stream source, string compendium = "", bool leaveOpen = false )
        {
            using ( var reader = new HkBinaryTagfileReader( source, compendium, leaveOpen ) )
            {
                // stuff
                reader.ReadCompendium();
                reader.ReadRootSection();
                // Console.WriteLine("FoundTypes: " + reader.mTypes.Count);
                return reader.mItems[ 1 ].Objects[ 0 ];
            }
        }

        public static IHkObject Read( string filePath, string compendium = "" )
        {
            using ( var source = File.OpenRead( filePath ) )
            {
                return Read( source, compendium );
            }
        }

        public static HkBinaryTagfileReader ReadCompendiums( Stream source, bool leaveOpen = false )
        {
            using ( var reader = new HkBinaryTagfileReader( source, "", leaveOpen ) )
            {
                // stuff
                reader.ReadRootSection();
                return reader;
            }
        }

        public static HkBinaryTagfileReader ReadCompendiums(string compendium)
        {
            using ( var source = File.OpenRead( compendium ) )
            {
                return ReadCompendiums( source );
            }
        }

        public void BackportTypesTo2012() {
            void LimitVersion(HkType type, int maxVer) {
                if (type != null && type.Version > maxVer) {
                    type.mVersion = maxVer;
                }
            }

            foreach (var type in mTypes) {
                var toRemoveTypes = new string[]
                {
                    "hkDefaultPropertyBag",
                    "hkHash",
                    "hkTuple",
                    "hkPropertyId",
                    "hkPtrAndInt",
                    "hkPropertyDesc",
                };
                mTypes.RemoveAll(x => toRemoveTypes.Contains(x.Name));
                
                if (type.Name == "hkReferencedObject") {
                    LimitVersion(type, 0);
                    type.mFields.RemoveAll(x => x.Name == "propertyBag");
                    type.mFields.ForEach(x => {
                        if (x.Name == "refCount") {
                            x.Name = "referenceCount";
                        }
                    });
                }
                
                if (type.Name == "hkxMeshSection") {
                    LimitVersion(type, 4);
                    type.mFields.RemoveAll(x => x.Name == "boneMatrixMap");
                }

                if (type.Name == "hkxVertexBuffer::VertexData") {
                    LimitVersion(type, 0);
                }
                
                if (type.Name == "hkxVertexDescription::ElementDecl") {
                    LimitVersion(type, 3);
                    type.mFields.RemoveAll(x => x.Name == "channelID");
                }

                if (type.Name == "hkxMaterial") {
                    LimitVersion(type, 4);
                    type.mFields.RemoveAll(x => x.Name == "userData");
                }

                if (type.Name == "hkaSkeleton") {
                    LimitVersion(type, 5);
                }

                if (type.Name == "hkcdStaticMeshTreeBase") {
                    LimitVersion(type, 0);
                    type.mFields.RemoveAll(x => x.Name == "primitiveStoresIsFlatConvex");
                }

                if (type.Name == "hkaInterleavedUncompressedAnimation") {
                    LimitVersion(type, 0);
                }

                if (type.Name == "hkpStaticCompoundShape") {
                    // TODO:
                    // type.mFields.ForEach(x => {
                    //     if (x.Name == "numBitsForChildShapeKey") {
                    //         
                    //     }
                    // });
                }

                if (type.Name == "hkpStaticCompoundShape::Instance") {
                    LimitVersion(type, 0);
                }

            }
        }

        private class Item
        {
            private readonly HkBinaryTagfileReader mTag;

            private List<IHkObject> mObjects;

            public Item( HkBinaryTagfileReader tag )
            {
                mTag = tag;

                int typeIndex = mTag.mReader.ReadInt32() & 0xFFFFFF;
                Type = typeIndex == 0 ? null : tag.mTypes[ typeIndex - 1 ];
                Position = mTag.mReader.ReadUInt32() + tag.mDataOffset;
                Count = mTag.mReader.ReadInt32();
            }

            private HkType Type { get; }
            private long Position { get; }
            private int Count { get; }

            public IReadOnlyList<IHkObject> Objects
            {
                get
                {
                    if ( mObjects == null )
                        ReadThisObject();

                    return mObjects;
                }
            }

            private void ReadThisObject()
            {
                if ( mObjects != null )
                    return;

                mObjects = new List<IHkObject>( Count );
                for ( int i = 0; i < Count; i++ )
                    mObjects.Add( ReadObject( Type, Position + i * Type.ByteSize ) );
            }

            private IHkObject ReadObject( HkType type, long offset )
            {
                mTag.mStream.Seek( offset, SeekOrigin.Begin );

                switch ( type.Format )
                {
                    case HkTypeFormat.Void:
                        return new HkVoid( type );

                    case HkTypeFormat.Opaque:
                        return new HkOpaque( type );

                    case HkTypeFormat.Bool:
                    {
                        bool value;

                        switch ( type.BitCount )
                        {
                            case 8:
                                value = mTag.mReader.ReadByte() != 0;
                                break;

                            case 16:
                                value = mTag.mReader.ReadInt16() != 0;
                                break;

                            case 32:
                                value = mTag.mReader.ReadInt32() != 0;
                                break;

                            case 64:
                                value = mTag.mReader.ReadInt64() != 0;
                                break;

                            default:
                                throw new InvalidDataException( $"Unexpected bit count: {type.BitCount}" );
                        }

                        return new HkBool( type, value );
                    }

                    case HkTypeFormat.String:
                    {
                        string value;
                        if ( type.IsFixedSize )
                        {
                            value = mTag.mReader.ReadString( type.FixedSize );
                        }
                        else
                        {
                            var item = ReadItemIndex();
                            if ( item != null )
                            {
                                var stringBuilder = new StringBuilder( item.Count - 1 );
                                for ( int i = 0; i < item.Count - 1; i++ )
                                    stringBuilder.Append( ( char ) ( byte ) item[ i ].Value );

                                value = stringBuilder.ToString();
                            }
                            else
                            {
                                value = null;
                            }
                        }

                        return new HkString( type, value );
                    }

                    case HkTypeFormat.Int:
                    {
                        switch ( type.BitCount )
                        {
                            case 8:
                                return type.IsSigned
                                    ? new HkSByte( type, mTag.mReader.ReadSByte() )
                                    : ( IHkObject ) new HkByte( type, mTag.mReader.ReadByte() );

                            case 16:
                                return type.IsSigned
                                    ? new HkInt16( type, mTag.mReader.ReadInt16() )
                                    : ( IHkObject ) new HkUInt16( type, mTag.mReader.ReadUInt16() );

                            case 32:
                                return type.IsSigned
                                    ? new HkInt32( type, mTag.mReader.ReadInt32() )
                                    : ( IHkObject ) new HkUInt32( type, mTag.mReader.ReadUInt32() );

                            case 64:
                                return type.IsSigned
                                    ? new HkInt64( type, mTag.mReader.ReadInt64() )
                                    : ( IHkObject ) new HkUInt64( type, mTag.mReader.ReadUInt64() );

                            default:
                                throw new InvalidDataException( $"Unexpected bit count: {type.BitCount}" );
                        }
                    }

                    case HkTypeFormat.FloatingPoint:
                        return type.IsSingle ? new HkSingle( type, mTag.mReader.ReadSingle() ) :
                            type.IsDouble ? ( IHkObject ) new HkDouble( type, mTag.mReader.ReadDouble() ) :
                            throw new InvalidDataException( "Unexpected floating point format" );

                    case HkTypeFormat.Ptr:
                        return new HkPtr( type, ReadItemIndex()?[ 0 ] );

                    case HkTypeFormat.Class:
                        return new HkClass( type,
                            type.AllFields.ToDictionary( x => x,
                                x => ReadObject( x.Type, offset + x.ByteOffset ) ) );

                    case HkTypeFormat.Array:
                    {
                        if ( !type.IsFixedSize )
                            return new HkArray( type, ReadItemIndex() );

                        var array = new IHkObject[ type.FixedSize ];
                        for ( int i = 0; i < array.Length; i++ )
                            array[ i ] = ReadObject( type.SubType, offset + i * type.SubType.ByteSize );

                        return new HkArray( type, array );
                    }

                    default:
                        throw new ArgumentOutOfRangeException( nameof( type.Format ) );
                }

                IReadOnlyList<IHkObject> ReadItemIndex()
                {
                    int index = mTag.mReader.ReadInt32();
                    return index == 0 ? null : mTag.mItems[ index ].Objects;
                }
            }
        }
    }
}