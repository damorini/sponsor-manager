p = "core/admin_widgets.py"
c = open(p, encoding="utf-8").read()
anc = """            except (ValueError, TypeError):
                return ['' for _ in self.languages]
        return [value.get(lang, '') for lang in self.languages]"""
new = """            except (ValueError, TypeError):
                return ['' for _ in self.languages]
        if not isinstance(value, dict):
            return ['' for _ in self.languages]
        return [value.get(lang, '') for lang in self.languages]"""
n = c.count(anc)
print("occorrenze trovate:", n)
if n >= 1:
    open(p,"w",encoding="utf-8").write(c.replace(anc,new))
    print("corretto", n, "punto/i")
else:
    print("ATTENZIONE: blocco non trovato")
