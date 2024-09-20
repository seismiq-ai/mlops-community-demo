# About the EDGAR API

Website: [EDGAR API](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
Example information: [Company Search Result: Apple Inc.](https://www.sec.gov/edgar/browse/?CIK=320193)


## Relevant schemas:

#### Submissions

```
interface SubmissionResponse {
  cik: string;
  entityType: string;
  sic: string;
  sicDescription: string;
  ownerOrg: string;
  insiderTransactionForOwnerExists: number;
  insiderTransactionForIssuerExists: number;
  name: string;
  tickers: string[];
  exchanges: string[];
  ein: string;
  description: string;
  website: string;
  investorWebsite: string;
  category: string;
  fiscalYearEnd: string;
  stateOfIncorporation: string;
  stateOfIncorporationDescription: string;
  addresses: {
    mailing: Address;
    business: Address;
  };
  phone: string;
  flags: string;
  formerNames: FormerName[];
  filings: {
    recent: {
      accessionNumber: string[];
      filingDate: string[];
    };
  };
}

interface Address {
  street1: string;
  street2: string | null;
  city: string;
  stateOrCountry: string;
  zipCode: string;
  stateOrCountryDescription: string;
}

interface FormerName {
  name: string;
  from: string;
  to: string;
}
```