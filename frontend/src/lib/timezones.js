// Comprehensive IANA timezone list (trimmed of deprecated links)
// Source compiled from CLDR + IANA. You can further reduce if needed.
export const TIMEZONES = [
  'UTC','Etc/UTC','Etc/GMT','Etc/GMT+0','Etc/GMT-0','Etc/GMT0','Etc/Greenwich','Etc/Universal','Etc/Zulu','Etc/UCT','Etc/UTC','Etc/Greenwich',
  'Africa/Abidjan','Africa/Accra','Africa/Addis_Ababa','Africa/Algiers','Africa/Asmara','Africa/Bamako','Africa/Bangui','Africa/Banjul','Africa/Bissau','Africa/Blantyre','Africa/Brazzaville','Africa/Bujumbura','Africa/Cairo','Africa/Casablanca','Africa/Ceuta','Africa/Conakry','Africa/Dakar','Africa/Dar_es_Salaam','Africa/Djibouti','Africa/Douala','Africa/El_Aaiun','Africa/Freetown','Africa/Gaborone','Africa/Harare','Africa/Johannesburg','Africa/Juba','Africa/Kampala','Africa/Khartoum','Africa/Kigali','Africa/Kinshasa','Africa/Lagos','Africa/Libreville','Africa/Lome','Africa/Luanda','Africa/Lubumbashi','Africa/Lusaka','Africa/Malabo','Africa/Maputo','Africa/Maseru','Africa/Mbabane','Africa/Mogadishu','Africa/Monrovia','Africa/Nairobi','Africa/Ndjamena','Africa/Niamey','Africa/Nouakchott','Africa/Ouagadougou','Africa/Porto-Novo','Africa/Sao_Tome','Africa/Tripoli','Africa/Tunis','Africa/Windhoek',
  'America/Adak','America/Anchorage','America/Anguilla','America/Antigua','America/Araguaina','America/Argentina/Buenos_Aires','America/Argentina/Catamarca','America/Argentina/Cordoba','America/Argentina/Jujuy','America/Argentina/La_Rioja','America/Argentina/Mendoza','America/Argentina/Rio_Gallegos','America/Argentina/Salta','America/Argentina/San_Juan','America/Argentina/San_Luis','America/Argentina/Tucuman','America/Argentina/Ushuaia','America/Aruba','America/Asuncion','America/Atikokan','America/Bahia','America/Bahia_Banderas','America/Barbados','America/Belem','America/Belize','America/Blanc-Sablon','America/Boa_Vista','America/Bogota','America/Boise','America/Cambridge_Bay','America/Campo_Grande','America/Cancun','America/Caracas','America/Cayenne','America/Cayman','America/Chicago','America/Chihuahua','America/Costa_Rica','America/Creston','America/Cuiaba','America/Curacao','America/Danmarkshavn','America/Dawson','America/Dawson_Creek','America/Denver','America/Detroit','America/Dominica','America/Edmonton','America/Eirunepe','America/El_Salvador','America/Fort_Nelson','America/Fortaleza','America/Glace_Bay','America/Godthab','America/Goose_Bay','America/Grand_Turk','America/Grenada','America/Guadeloupe','America/Guatemala','America/Guayaquil','America/Guyana','America/Halifax','America/Havana','America/Hermosillo','America/Indiana/Indianapolis','America/Indiana/Knox','America/Indiana/Marengo','America/Indiana/Petersburg','America/Indiana/Tell_City','America/Indiana/Vevay','America/Indiana/Vincennes','America/Indiana/Winamac','America/Inuvik','America/Iqaluit','America/Jamaica','America/Juneau','America/Kentucky/Louisville','America/Kentucky/Monticello','America/La_Paz','America/Lima','America/Los_Angeles','America/Maceio','America/Managua','America/Manaus','America/Marigot','America/Martinique','America/Matamoros','America/Mazatlan','America/Menominee','America/Merida','America/Metlakatla','America/Mexico_City','America/Miquelon','America/Moncton','America/Monterrey','America/Montevideo','America/Montserrat','America/Nassau','America/New_York','America/Nipigon','America/Nome','America/Noronha','America/North_Dakota/Beulah','America/North_Dakota/Center','America/North_Dakota/New_Salem','America/Ojinaga','America/Panama','America/Pangnirtung','America/Paramaribo','America/Phoenix','America/Port-au-Prince','America/Port_of_Spain','America/Porto_Velho','America/Puerto_Rico','America/Punta_Arenas','America/Rainy_River','America/Rankin_Inlet','America/Recife','America/Regina','America/Resolute','America/Rio_Branco','America/Santarem','America/Santiago','America/Santo_Domingo','America/Sao_Paulo','America/Scoresbysund','America/Sitka','America/St_Barthelemy','America/St_Johns','America/St_Kitts','America/St_Lucia','America/St_Thomas','America/St_Vincent','America/Swift_Current','America/Tegucigalpa','America/Thule','America/Thunder_Bay','America/Tijuana','America/Toronto','America/Vancouver','America/Whitehorse','America/Winnipeg','America/Yakutat','America/Yellowknife',
  'Antarctica/Casey','Antarctica/Davis','Antarctica/DumontDUrville','Antarctica/Macquarie','Antarctica/Mawson','Antarctica/Palmer','Antarctica/Rothera','Antarctica/Syowa','Antarctica/Troll','Antarctica/Vostok',
  'Arctic/Longyearbyen','Asia/Aden','Asia/Almaty','Asia/Amman','Asia/Anadyr','Asia/Aqtau','Asia/Aqtobe','Asia/Ashgabat','Asia/Atyrau','Asia/Baghdad','Asia/Bahrain','Asia/Baku','Asia/Bangkok','Asia/Barnaul','Asia/Beirut','Asia/Bishkek','Asia/Brunei','Asia/Chita','Asia/Choibalsan','Asia/Colombo','Asia/Damascus','Asia/Dhaka','Asia/Dili','Asia/Dubai','Asia/Dushanbe','Asia/Famagusta','Asia/Gaza','Asia/Hebron','Asia/Ho_Chi_Minh','Asia/Hong_Kong','Asia/Hovd','Asia/Irkutsk','Asia/Jakarta','Asia/Jayapura','Asia/Jerusalem','Asia/Kabul','Asia/Kamchatka','Asia/Karachi','Asia/Kathmandu','Asia/Khandyga','Asia/Kolkata','Asia/Krasnoyarsk','Asia/Kuala_Lumpur','Asia/Kuching','Asia/Kuwait','Asia/Macau','Asia/Magadan','Asia/Makassar','Asia/Manila','Asia/Muscat','Asia/Nicosia','Asia/Novokuznetsk','Asia/Novosibirsk','Asia/Omsk','Asia/Oral','Asia/Phnom_Penh','Asia/Pontianak','Asia/Pyongyang','Asia/Qatar','Asia/Qostanay','Asia/Qyzylorda','Asia/Riyadh','Asia/Sakhalin','Asia/Samarkand','Asia/Seoul','Asia/Shanghai','Asia/Singapore','Asia/Srednekolymsk','Asia/Taipei','Asia/Tashkent','Asia/Tbilisi','Asia/Tehran','Asia/Thimphu','Asia/Tokyo','Asia/Tomsk','Asia/Ulaanbaatar','Asia/Urumqi','Asia/Ust-Nera','Asia/Vladivostok','Asia/Yakutsk','Asia/Yangon','Asia/Yekaterinburg','Asia/Yerevan',
  'Atlantic/Azores','Atlantic/Bermuda','Atlantic/Canary','Atlantic/Cape_Verde','Atlantic/Faroe','Atlantic/Madeira','Atlantic/Reykjavik','Atlantic/South_Georgia','Atlantic/Stanley',
  'Australia/Adelaide','Australia/Brisbane','Australia/Broken_Hill','Australia/Darwin','Australia/Eucla','Australia/Hobart','Australia/Lindeman','Australia/Lord_Howe','Australia/Melbourne','Australia/Perth','Australia/Sydney',
  'Europe/Amsterdam','Europe/Andorra','Europe/Athens','Europe/Belgrade','Europe/Berlin','Europe/Bratislava','Europe/Brussels','Europe/Bucharest','Europe/Budapest','Europe/Busingen','Europe/Chisinau','Europe/Copenhagen','Europe/Dublin','Europe/Gibraltar','Europe/Guernsey','Europe/Helsinki','Europe/Isle_of_Man','Europe/Istanbul','Europe/Jersey','Europe/Kaliningrad','Europe/Kiev','Europe/Kirov','Europe/Lisbon','Europe/Ljubljana','Europe/London','Europe/Luxembourg','Europe/Madrid','Europe/Malta','Europe/Mariehamn','Europe/Minsk','Europe/Monaco','Europe/Moscow','Europe/Oslo','Europe/Paris','Europe/Podgorica','Europe/Prague','Europe/Riga','Europe/Rome','Europe/Samara','Europe/San_Marino','Europe/Sarajevo','Europe/Saratov','Europe/Simferopol','Europe/Skopje','Europe/Sofia','Europe/Stockholm','Europe/Tallinn','Europe/Tirane','Europe/Ulyanovsk','Europe/Vaduz','Europe/Vatican','Europe/Vienna','Europe/Vilnius','Europe/Volgograd','Europe/Warsaw','Europe/Zagreb','Europe/Zurich',
  'Indian/Antananarivo','Indian/Chagos','Indian/Christmas','Indian/Cocos','Indian/Comoro','Indian/Kerguelen','Indian/Mahe','Indian/Maldives','Indian/Mauritius','Indian/Mayotte','Indian/Reunion',
  'Pacific/Apia','Pacific/Auckland','Pacific/Bougainville','Pacific/Chatham','Pacific/Chuuk','Pacific/Easter','Pacific/Efate','Pacific/Enderbury','Pacific/Fakaofo','Pacific/Fiji','Pacific/Funafuti','Pacific/Galapagos','Pacific/Gambier','Pacific/Guadalcanal','Pacific/Guam','Pacific/Honolulu','Pacific/Kanton','Pacific/Kiritimati','Pacific/Kosrae','Pacific/Kwajalein','Pacific/Majuro','Pacific/Marquesas','Pacific/Midway','Pacific/Nauru','Pacific/Niue','Pacific/Norfolk','Pacific/Noumea','Pacific/Pago_Pago','Pacific/Palau','Pacific/Pitcairn','Pacific/Pohnpei','Pacific/Port_Moresby','Pacific/Rarotonga','Pacific/Saipan','Pacific/Tahiti','Pacific/Tarawa','Pacific/Tongatapu','Pacific/Wake','Pacific/Wallis'
];

export function formatOffset(tz) {
  try {
    const sample = new Intl.DateTimeFormat('en-US', { timeZone: tz, timeZoneName: 'short' }).format(new Date());
    const match = sample.match(/GMT([+-]\d{1,2})(:?([0-9]{2}))?/);
    if (match) {
      let h = match[1];
      if (h.length === 2 && (h[0] === '+' || h[0] === '-')) h = h[0] + '0' + h[1];
      let m = match[3] || '00';
      return `UTC${h}:${m}`;
    }
  } catch(_) {}
  return 'UTC';
}

export function getTimezonesWithOffsets() {
  const now = Date.now();
  return TIMEZONES.map(tz => ({ tz, label: `${tz} (${formatOffset(tz)})` }));
}

/**
 * Curated timezone options with user-friendly labels (major cities and regions).
 * This provides a more manageable list for the settings dropdown.
 */
export const TIMEZONE_OPTIONS = [
  // North America - Pacific
  { value: 'America/Los_Angeles', label: 'Pacific Time (Los Angeles)' },
  { value: 'America/Vancouver', label: 'Pacific Time (Vancouver)' },
  { value: 'America/Tijuana', label: 'Pacific Time (Tijuana)' },
  
  // North America - Mountain
  { value: 'America/Denver', label: 'Mountain Time (Denver)' },
  { value: 'America/Phoenix', label: 'Mountain Time - Arizona (Phoenix)' },
  { value: 'America/Edmonton', label: 'Mountain Time (Edmonton)' },
  { value: 'America/Chihuahua', label: 'Mountain Time (Chihuahua)' },
  
  // North America - Central
  { value: 'America/Chicago', label: 'Central Time (Chicago)' },
  { value: 'America/Mexico_City', label: 'Central Time (Mexico City)' },
  { value: 'America/Winnipeg', label: 'Central Time (Winnipeg)' },
  
  // North America - Eastern
  { value: 'America/New_York', label: 'Eastern Time (New York)' },
  { value: 'America/Toronto', label: 'Eastern Time (Toronto)' },
  { value: 'America/Detroit', label: 'Eastern Time (Detroit)' },
  
  // North America - Atlantic
  { value: 'America/Halifax', label: 'Atlantic Time (Halifax)' },
  { value: 'America/Puerto_Rico', label: 'Atlantic Time (Puerto Rico)' },
  
  // North America - Alaska & Hawaii
  { value: 'America/Anchorage', label: 'Alaska Time (Anchorage)' },
  { value: 'Pacific/Honolulu', label: 'Hawaii Time (Honolulu)' },
  
  // Europe - Western
  { value: 'Europe/London', label: 'UK Time (London)' },
  { value: 'Europe/Dublin', label: 'Irish Time (Dublin)' },
  { value: 'Europe/Lisbon', label: 'Western Europe (Lisbon)' },
  
  // Europe - Central
  { value: 'Europe/Paris', label: 'Central Europe (Paris)' },
  { value: 'Europe/Berlin', label: 'Central Europe (Berlin)' },
  { value: 'Europe/Madrid', label: 'Central Europe (Madrid)' },
  { value: 'Europe/Rome', label: 'Central Europe (Rome)' },
  { value: 'Europe/Amsterdam', label: 'Central Europe (Amsterdam)' },
  { value: 'Europe/Brussels', label: 'Central Europe (Brussels)' },
  { value: 'Europe/Vienna', label: 'Central Europe (Vienna)' },
  { value: 'Europe/Stockholm', label: 'Central Europe (Stockholm)' },
  { value: 'Europe/Zurich', label: 'Central Europe (Zurich)' },
  
  // Europe - Eastern
  { value: 'Europe/Athens', label: 'Eastern Europe (Athens)' },
  { value: 'Europe/Helsinki', label: 'Eastern Europe (Helsinki)' },
  { value: 'Europe/Istanbul', label: 'Turkey (Istanbul)' },
  { value: 'Europe/Bucharest', label: 'Eastern Europe (Bucharest)' },
  { value: 'Europe/Kiev', label: 'Eastern Europe (Kyiv)' },
  
  // Europe - Moscow
  { value: 'Europe/Moscow', label: 'Moscow Time (Moscow)' },
  
  // Asia - Middle East
  { value: 'Asia/Dubai', label: 'Gulf Time (Dubai)' },
  { value: 'Asia/Tehran', label: 'Iran Time (Tehran)' },
  { value: 'Asia/Jerusalem', label: 'Israel Time (Jerusalem)' },
  { value: 'Asia/Riyadh', label: 'Arabia Time (Riyadh)' },
  
  // Asia - South
  { value: 'Asia/Kolkata', label: 'India Time (Mumbai/Kolkata)' },
  { value: 'Asia/Karachi', label: 'Pakistan Time (Karachi)' },
  { value: 'Asia/Dhaka', label: 'Bangladesh Time (Dhaka)' },
  
  // Asia - Southeast
  { value: 'Asia/Bangkok', label: 'Indochina Time (Bangkok)' },
  { value: 'Asia/Singapore', label: 'Singapore Time (Singapore)' },
  { value: 'Asia/Jakarta', label: 'Western Indonesia (Jakarta)' },
  { value: 'Asia/Manila', label: 'Philippine Time (Manila)' },
  { value: 'Asia/Ho_Chi_Minh', label: 'Indochina Time (Ho Chi Minh City)' },
  
  // Asia - East
  { value: 'Asia/Hong_Kong', label: 'Hong Kong Time (Hong Kong)' },
  { value: 'Asia/Shanghai', label: 'China Time (Shanghai/Beijing)' },
  { value: 'Asia/Taipei', label: 'Taiwan Time (Taipei)' },
  { value: 'Asia/Seoul', label: 'Korea Time (Seoul)' },
  { value: 'Asia/Tokyo', label: 'Japan Time (Tokyo)' },
  
  // Australia & Pacific
  { value: 'Australia/Perth', label: 'Australian Western Time (Perth)' },
  { value: 'Australia/Adelaide', label: 'Australian Central Time (Adelaide)' },
  { value: 'Australia/Darwin', label: 'Australian Central Time (Darwin)' },
  { value: 'Australia/Brisbane', label: 'Australian Eastern Time (Brisbane)' },
  { value: 'Australia/Sydney', label: 'Australian Eastern Time (Sydney)' },
  { value: 'Australia/Melbourne', label: 'Australian Eastern Time (Melbourne)' },
  { value: 'Pacific/Auckland', label: 'New Zealand Time (Auckland)' },
  { value: 'Pacific/Fiji', label: 'Fiji Time (Fiji)' },
  
  // South America
  { value: 'America/Sao_Paulo', label: 'Brazil Time (São Paulo)' },
  { value: 'America/Argentina/Buenos_Aires', label: 'Argentina Time (Buenos Aires)' },
  { value: 'America/Santiago', label: 'Chile Time (Santiago)' },
  { value: 'America/Lima', label: 'Peru Time (Lima)' },
  { value: 'America/Bogota', label: 'Colombia Time (Bogotá)' },
  { value: 'America/Caracas', label: 'Venezuela Time (Caracas)' },
  
  // Africa
  { value: 'Africa/Cairo', label: 'Egypt Time (Cairo)' },
  { value: 'Africa/Lagos', label: 'West Africa Time (Lagos)' },
  { value: 'Africa/Johannesburg', label: 'South Africa Time (Johannesburg)' },
  { value: 'Africa/Nairobi', label: 'East Africa Time (Nairobi)' },
  
  // UTC
  { value: 'UTC', label: 'UTC (Coordinated Universal Time)' },
];

/**
 * Get a user-friendly timezone label from IANA timezone string.
 * Falls back to the raw timezone if not found in our curated list.
 */
export const getTimezoneLabel = (timezone) => {
  if (!timezone) return null;
  const option = TIMEZONE_OPTIONS.find(opt => opt.value === timezone);
  return option ? option.label : timezone;
};

/**
 * Detect the device timezone and return both the IANA string and friendly label.
 */
export const detectDeviceTimezoneInfo = () => {
  try {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const label = getTimezoneLabel(tz) || `${tz} (${formatOffset(tz)})`;
    return { value: tz, label };
  } catch {
    return { value: 'UTC', label: 'UTC (Coordinated Universal Time)' };
  }
};
