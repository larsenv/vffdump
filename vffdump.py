#!/usr/bin/python

import sys, array, struct, os, os.path

class FAT(object):
    def __init__(self, fd, clustercount, clustersize):
        # WARNING: LITTLE ENDIAN HOST ONLY
        if clustercount > 0xFFF5:
            raise Exception("FAT32 not supported yet")
        elif clustercount > 0xFF5:
            # FAT16
            self.fat = 16
            fatsize = clustercount * 2
            self.rsvd = 0xfff0
            code = 'H'
        else:
            # FAT12
            self.fat = 12
            fatsize = ((clustercount + 1) // 2) * 3
            self.rsvd = 0xff0
            code = 'B'

        data = fd.read((fatsize + clustersize - 1) & ~(clustersize-1))
        self.array = array.array(code,data)
        
        if not self.is_reserved(self[0]):
            raise Exception("Failed to parse FAT: expected first entry to be reserved, fount 0x%x" % self[0])

    def is_available(self, x):
        return x == 0x0000

    def is_used(self, x):
        return 0x0001 <= x < self.rsvd

    def is_reserved(self, x):
        return self.rsvd <= x <= (self.rsvd + 6)

    def is_bad(self, x):
        return x == (self.rsvd + 7)

    def is_last(self, x):
        return (self.rsvd + 8) <= x

    def __getitem__(self, item):
        if self.fat == 16:
            return self.array[item]
        off = (item // 2) * 3
        return (
            (self.array[off + 1] >> 4) | (self.array[off + 2] << 4)
            if item & 1
            else self.array[off] | ((self.array[off + 1] & 0xF) << 8)
        )

    def get_chain(self,start):
        chain = []
        clus = start
        while self.is_used(clus):
            chain.append(clus)
            clus = self[clus]
        if not self.is_last(clus):
            raise Exception("Found 0x%04x in cluster chain"%clus)
        return chain

class Directory(object):
    A_R = 1
    A_H = 2
    A_S = 4
    A_VL = 8
    A_DIR = 16
    A_A = 32
    A_DEV = 64
    def __init__(self, vff, data):
        self.vff = vff
        self.data = data

    def read(self):
        files = []
        for i in range(0, len(self.data), 32):
            d = self.data[i:i+32]
            #print repr(d)
            name, ext, attr, rsv, cms, ctime, cdate, adate, eaindex, mtime, mdate, start, size = struct.unpack(
                "<8s3sBBBHHHHHHHI", d)
            #<print repr(name)+repr(ext)
            if name[0] in "\xe5\x00":
                continue
            if attr & 0xf == 0xf:
                continue
            fullname = f"{name.rstrip()}.{ext.rstrip()}"
            if fullname[-1] == ".":
                fullname = fullname[:-1]
            files.append((fullname, attr, start, size))
        return files

    def ls(self, t=""):
        for name, attr, start, size in self.read():
            if attr & self.A_DIR:

                if name in [".",".."]:
                    continue
                print t + "/%s/"%name

                self[name].ls(t + "/" + name)
            else:
                print t + "/" + name + " [0x%x]"%size

    def dump(self, path):
        if not os.path.isdir(path):
            os.mkdir(path)
        for name, attr, start, size in self.read():
            if attr & self.A_DIR:

                if name in [".",".."]:
                    continue
                print " " + path + "/%s/"%name
                self[name].dump(path + "/" + name)
            else:
                print " " + path + "/" + name + " [0x%x]"%size
                f = open(path + "/" + name,"wb")
                f.write(self[name])
                f.close()

    def __getitem__(self, d):
        for name, attr, start, size in self.read():
            if name.lower() == d.lower():
                if attr & self.A_DIR:
                    return Directory(self.vff,self.vff.read_chain(start))
                elif not size:
                    return ""
                else:
                    return self.vff.read_chain(start)[:size]


class VFF(object):
    def __init__(self, file):
        self.fd = open(file, "rb")

        hdrdat = self.fd.read(0x20)[:0x10]
        magic, unk, volsize, clussize = struct.unpack(">4sIIHxx", hdrdat)

        self.volume_size = volsize
        self.cluster_size = clussize * 16 # ??
        self.cluster_count = self.volume_size / self.cluster_size

        print "volume size: 0x%x"%self.volume_size
        print "cluster size: 0x%x"%self.cluster_size
        print "cluster count: 0x%x"%self.cluster_count

        self.fat1 = FAT(self.fd, self.cluster_count, self.cluster_size)
        self.fat2 = FAT(self.fd, self.cluster_count, self.cluster_size)

        print "FAT type: FAT%d" % self.fat1.fat
        print "FAT1: %x"%self.fat1[0]
        print "FAT2: %x"%self.fat2[0]

        print "Data offset: 0x%x"%self.fd.tell()

        self.root = Directory(self, self.fd.read(0x1000))

        self.offset = self.fd.tell()

    def read_cluster(self, num):
        num -= 2
        self.fd.seek(self.offset + self.cluster_size * num)
        return self.fd.read(self.cluster_size)

    def read_chain(self, start):
        clusters = self.fat1.get_chain(start)
        return "".join(self.read_cluster(c) for c in clusters)



v = VFF(sys.argv[1])

print "Directory listing: "
v.root.ls(" ")
if len(sys.argv) > 2:
    print
    print "Dumping..."
    v.root.dump(sys.argv[2])


