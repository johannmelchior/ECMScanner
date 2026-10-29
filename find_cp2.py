import sys, struct
sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, r"C:\Users\johan\Documents\projetoCAN\python-code")
from disasm_nav import read_class

path = r"C:\Users\johan\Documents\projetoCAN\temp_jar_extract\diagfw\com\kpit\diagfw\application\ApplicationEditorAdvisor.class"
data = read_class(path)
cp_count = struct.unpack_from(">H", data, 8)[0]
pos = 10
cp = [None]
i = 1
while i < cp_count:
    tag = data[pos]; pos += 1
    if tag == 1:
        l = struct.unpack_from(">H", data, pos)[0]; pos += 2
        s = data[pos:pos+l].decode("utf-8", errors="replace"); pos += l
        cp.append(("Utf8", s))
    elif tag in (3,4,9,10,11,12): pos += 4; cp.append(("skip",))
    elif tag in (5,6): pos += 8; cp.append(("skip",)); cp.append(None); i += 1
    elif tag == 7: idx2=struct.unpack_from(">H",data,pos)[0]; pos+=2; cp.append(("Class",idx2))
    elif tag == 8: idx2=struct.unpack_from(">H",data,pos)[0]; pos+=2; cp.append(("String",idx2))
    elif tag in (16,): pos += 2; cp.append(("skip",))
    elif tag == 15: pos += 3; cp.append(("skip",))
    elif tag == 18: pos += 4; cp.append(("skip",))
    else: cp.append(("skip",))
    i += 1

# Show String tags and their resolved values
print("String constants:")
for idx, e in enumerate(cp):
    if e and e[0] == "String":
        val_idx = e[1]
        if val_idx < len(cp) and cp[val_idx] and cp[val_idx][0] == "Utf8":
            val = cp[val_idx][1]
            print(f"  CP[{idx}] String -> [{val_idx}] = {val!r}")

print()
print("All Utf8 containing 'summary' or 'Summary':")
for idx, e in enumerate(cp):
    if e and e[0] == "Utf8" and "summary" in e[1].lower():
        print(f"  CP[{idx}] = {e[1]!r}")
