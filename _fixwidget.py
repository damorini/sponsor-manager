p = "core/admin_widgets.py"
c = open(p, encoding="utf-8").read()
if "if not isinstance(value, dict):" in c:
    print("gia' corretto")
else:
    anc = """            except (ValueError, TypeError):
                return ['' for _ in self.languages]
        return [value.get(lang, '') for lang in self.languages]"""
    new = """            except (ValueError, TypeError):
                return ['' for _ in self.languages]
        if not isinstance(value, dict):
            return ['' for _ in self.languages]
        return [value.get(lang, '') for lang in self.languages]"""
    if anc in c:
        open(p,"w",encoding="utf-8").write(c.replace(anc,new,1))
        print("widget corretto")
    else:
        print("ATTENZIONE: ancora non trovata")
