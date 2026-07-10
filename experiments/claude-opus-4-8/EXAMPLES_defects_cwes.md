# Example Claude generations with defects / CWEs

Snippets from `predictions.jsonl`; findings reproduced with the benchmark's own
analyzers (pylint/PMD/clang-tidy + Semgrep with the vendored rules).


## `python:gp188955` — SQL injection

**Task:** `def insert(self, **kwargs)` (python, stratum vulnerability_consensus)

```python
def insert(self, **kwargs):
    """Perform an INSERT statement on the model's table in the master database."""
    columns = list(kwargs.keys())
    values = [kwargs[column] for column in columns]

    placeholders = ", ".join(["%s"] * len(values))
    column_list = ", ".join(columns)
    query = "INSERT INTO {table} ({columns}) VALUES ({placeholders})".format(
        table=self.table_name, columns=column_list, placeholders=placeholders)

    connection = self.master
    cursor = connection.cursor()
    try:
        cursor.execute(query, values)
        connection.commit()
    finally:
        cursor.close()

```


**Vulnerabilities (CWE):**
- CWE-89: Improper Neutralization of Special Elements used in an SQL Command ('SQL Injection') `sqlalchemy-execute-raw-query` [ERROR] (line 14): Avoiding SQL string concatenation: untrusted input concatenated with raw SQL query can result in SQL Injection. In order to execute raw query safely, prepared s


## `python:gp079241` — defect (pylint/ODC)

**Task:** `def do_ctrlc(self, arg)` (python, stratum defect_consensus)

```python
def do_ctrlc(self, arg):
    """Ctrl-C sends a STOP command to the arm."""
    self.arm.stop()
    return False

```

**Defects (ODC):**
- `unused-argument` → ODC Assignment (line 1): Unused argument 'arg'


## `java:gj168975` — defect (PMD/ODC)

**Task:** `public static synchronized void bootstrap(String[] args, String... extraArgs)` (java, stratum defect_consensus)

```java
public static synchronized void bootstrap(String[] args, String... extraArgs) {
    init(args, extraArgs);
    beans();
    ready();
}
```

**Defects (ODC):**
- `AvoidSynchronizedAtMethodLevel` → ODC Timing (line 2): Use block level locking rather than method level synchronization


## `c:a866dbb55f4bafed1055da535dd2e776438863ab` — buffer overflow

**Task:** `pltsql_get_source(int startlocation, int length)` (c, stratum mixed_consensus)

```c
#include <string.h>

/* Original text being scanned by the lexer. */
extern char *scanorig;

char *
pltsql_get_source(int startlocation, int length)
{
    char *result = (char *) palloc(length + 1);

    memcpy(result, scanorig + startlocation, length);
    result[length] = '\0';

    return result;
}
```

**Defects (ODC):**
- `cppcoreguidelines-avoid-non-const-global-variables` → ODC Interface (line 4): variable 'scanorig' is non-const and globally accessible, consider making it const
- `performance-no-int-to-ptr` → ODC Assignment (line 9): integer to pointer cast pessimizes optimization opportunities

**Vulnerabilities (CWE):**
- CWE-120 `bcopy-1` [INFO] (line 11): The `memcpy` family of functions require the developer to validate that the destination buffer is the same size or larger than the source buffer. Buffer overflo


## `c:4ab87ad6783309e823fdd3c9c9052726df7f45aa` — OS command injection

**Task:** `static int compareOutput(char *cmd, char *expected)` (c, stratum mixed_consensus)

```c
#include <stdio.h>

static int compareOutput(char *cmd, char *expected)
{
	FILE *cmd_fp;
	FILE *exp_fp;
	int a, b;
	int result = 1;

	cmd_fp = popen(cmd, "r");
	if (cmd_fp == NULL)
		return 0;

	exp_fp = fopen(expected, "r");
	if (exp_fp == NULL) {
		pclose(cmd_fp);
		return 0;
	}

	do {
		a = fgetc(cmd_fp);
		b = fgetc(exp_fp);
		if (a != b) {
			result = 0;
			break;
		}
	} while (a != EOF);

	pclose(cmd_fp);
	fclose(exp_fp);

	return result;
}
```

**Defects (ODC):**
- `bugprone-easily-swappable-parameters` → ODC Interface (line 3): 2 adjacent parameters of 'compareOutput' of similar type ('char *') are easily swapped by mistake
- `cert-env33-c` → ODC Interface (line 10): calling 'popen' uses a command processor
- `cert-err33-c` → ODC Checking (line 30): the value returned by this function should not be disregarded; neglecting it may lead to errors

**Vulnerabilities (CWE):**
- CWE-78 `ShellExecute-1` [ERROR] (line 10): It is generally not recommended to call out to the operating system to execute commands. When the application is executing file system based commands, user inpu
- CWE-362 `open-1` [INFO] (line 14): Usage of the `open` family of functions may hint at a potential Time Of Check Time Of Use (TOCTOU) vulnerability. An attacker may be able to modify the file bei
